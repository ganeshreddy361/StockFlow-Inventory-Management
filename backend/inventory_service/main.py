
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.auth_service.security import get_current_user


app = FastAPI(
    title="Inventory Service",
    description="Manage stock levels, reservations, and inventory history",
    version="1.1.0",
)

DATABASE = os.path.join(os.path.dirname(__file__), "inventory.db")


def get_connection():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(get_connection()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                product_id INTEGER PRIMARY KEY,
                quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
                updated_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                change_quantity INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        connection.commit()


initialize_database()


class StockUpdate(BaseModel):
    product_id: int = Field(gt=0)
    change_quantity: int = Field(ne=0, ge=-1000000, le=1000000)
    reason: str = Field(min_length=3, max_length=200)


class StockReservation(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)
    reason: str = Field(
        default="Order reservation",
        min_length=3,
        max_length=200,
    )


def staff_only(user: dict = Depends(get_current_user)):
    if user["role"] not in ("Admin", "Inventory Manager"):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )
    return user


@app.get("/")
def root():
    return {
        "service": "Inventory Service",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "service": "inventory",
        "status": "healthy",
    }


@app.get("/stock/{product_id}")
def get_stock(
    product_id: int,
    user: dict = Depends(get_current_user),
):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM inventory WHERE product_id = ?",
            (product_id,),
        ).fetchone()

    if row is None:
        return {
            "product_id": product_id,
            "quantity": 0,
        }

    return dict(row)


@app.post("/stock/adjust")
def adjust_stock(
    request: StockUpdate,
    user: dict = Depends(staff_only),
):
    now = datetime.now(timezone.utc).isoformat()

    with closing(get_connection()) as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            "SELECT quantity FROM inventory WHERE product_id = ?",
            (request.product_id,),
        ).fetchone()

        current_quantity = row["quantity"] if row else 0
        new_quantity = current_quantity + request.change_quantity

        if new_quantity < 0:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="Stock cannot become negative",
            )

        connection.execute(
            """
            INSERT INTO inventory (product_id, quantity, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                quantity = excluded.quantity,
                updated_at = excluded.updated_at
            """,
            (request.product_id, new_quantity, now),
        )

        connection.execute(
            """
            INSERT INTO stock_movements
                (product_id, change_quantity, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                request.product_id,
                request.change_quantity,
                request.reason.strip(),
                now,
            ),
        )

        connection.commit()

    return {
        "message": "Stock adjusted successfully",
        "product_id": request.product_id,
        "previous_quantity": current_quantity,
        "new_quantity": new_quantity,
    }


@app.post("/stock/reserve")
def reserve_stock(
    request: StockReservation,
    user: dict = Depends(get_current_user),
):
    """Atomically reserve stock for an order."""
    now = datetime.now(timezone.utc).isoformat()

    with closing(get_connection()) as connection:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            "SELECT quantity FROM inventory WHERE product_id = ?",
            (request.product_id,),
        ).fetchone()

        current_quantity = row["quantity"] if row else 0

        if current_quantity < request.quantity:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Insufficient stock",
                    "product_id": request.product_id,
                    "available": current_quantity,
                    "requested": request.quantity,
                },
            )

        new_quantity = current_quantity - request.quantity

        connection.execute(
            """
            UPDATE inventory
            SET quantity = ?, updated_at = ?
            WHERE product_id = ?
            """,
            (new_quantity, now, request.product_id),
        )

        connection.execute(
            """
            INSERT INTO stock_movements
                (product_id, change_quantity, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                request.product_id,
                -request.quantity,
                request.reason.strip(),
                now,
            ),
        )

        connection.commit()

    return {
        "message": "Stock reserved successfully",
        "product_id": request.product_id,
        "previous_quantity": current_quantity,
        "reserved_quantity": request.quantity,
        "remaining_quantity": new_quantity,
    }


@app.get("/stock/{product_id}/history")
def stock_history(
    product_id: int,
    user: dict = Depends(get_current_user),
):
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT * FROM stock_movements
            WHERE product_id = ?
            ORDER BY id DESC
            """,
            (product_id,),
        ).fetchall()

    return {
        "product_id": product_id,
        "movements": [dict(row) for row in rows],
    }

class BatchStockReservation(BaseModel):
    items: list[StockReservation] = Field(min_length=1, max_length=100)


@app.post("/stock/reserve-batch")
def reserve_stock_batch(
    request: BatchStockReservation,
    user: dict = Depends(get_current_user),
):
    """Reserve stock for multiple products in one database transaction."""
    now = datetime.now(timezone.utc).isoformat()

    # Combine duplicate product IDs so quantities are checked together.
    quantities = {}
    for item in request.items:
        quantities[item.product_id] = (
            quantities.get(item.product_id, 0) + item.quantity
        )

    with closing(get_connection()) as connection:
        connection.execute("BEGIN IMMEDIATE")

        for product_id, quantity in quantities.items():
            row = connection.execute(
                "SELECT quantity FROM inventory WHERE product_id = ?",
                (product_id,),
            ).fetchone()

            available = row["quantity"] if row else 0

            if available < quantity:
                connection.rollback()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Insufficient stock",
                        "product_id": product_id,
                        "available": available,
                        "requested": quantity,
                    },
                )

        results = []

        for product_id, quantity in quantities.items():
            row = connection.execute(
                "SELECT quantity FROM inventory WHERE product_id = ?",
                (product_id,),
            ).fetchone()

            previous_quantity = row["quantity"]
            new_quantity = previous_quantity - quantity

            connection.execute(
                """
                UPDATE inventory
                SET quantity = ?, updated_at = ?
                WHERE product_id = ?
                """,
                (new_quantity, now, product_id),
            )

            connection.execute(
                """
                INSERT INTO stock_movements
                    (product_id, change_quantity, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (product_id, -quantity, "Batch order reservation", now),
            )

            results.append({
                "product_id": product_id,
                "previous_quantity": previous_quantity,
                "reserved_quantity": quantity,
                "remaining_quantity": new_quantity,
            })

        connection.commit()

    return {
        "message": "Batch stock reservation successful",
        "items": results,
    }

class StockReleaseItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)


class BatchStockRelease(BaseModel):
    order_id: int = Field(gt=0)
    items: list[StockReleaseItem] = Field(min_length=1, max_length=100)


@app.post("/stock/release-batch")
def release_stock_batch(
    request: BatchStockRelease,
    user: dict = Depends(get_current_user),
):
    """Restore stock for a cancelled order exactly once per order ID."""
    now = datetime.now(timezone.utc).isoformat()
    quantities = {}
    for item in request.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    with closing(get_connection()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS inventory_releases (
                order_id INTEGER PRIMARY KEY,
                released_at TEXT NOT NULL
            )
        """)
        already_released = connection.execute(
            "SELECT order_id FROM inventory_releases WHERE order_id = ?",
            (request.order_id,),
        ).fetchone()
        if already_released:
            connection.commit()
            return {
                "message": "Inventory was already released for this order",
                "order_id": request.order_id,
                "already_released": True,
            }

        results = []
        for product_id, quantity in quantities.items():
            row = connection.execute(
                "SELECT quantity FROM inventory WHERE product_id = ?",
                (product_id,),
            ).fetchone()
            previous_quantity = row["quantity"] if row else 0
            new_quantity = previous_quantity + quantity
            connection.execute(
                """INSERT INTO inventory (product_id, quantity, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(product_id) DO UPDATE SET
                       quantity = excluded.quantity,
                       updated_at = excluded.updated_at""",
                (product_id, new_quantity, now),
            )
            connection.execute(
                """INSERT INTO stock_movements
                   (product_id, change_quantity, reason, created_at)
                   VALUES (?, ?, ?, ?)""",
                (product_id, quantity, f"Order {request.order_id} cancellation release", now),
            )
            results.append({
                "product_id": product_id,
                "restored_quantity": quantity,
                "previous_quantity": previous_quantity,
                "new_quantity": new_quantity,
            })

        connection.execute(
            "INSERT INTO inventory_releases (order_id, released_at) VALUES (?, ?)",
            (request.order_id, now),
        )
        connection.commit()

    return {
        "message": "Inventory released successfully",
        "order_id": request.order_id,
        "already_released": False,
        "items": results,
    }

