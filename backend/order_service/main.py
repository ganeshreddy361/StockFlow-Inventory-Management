import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.auth_service.security import get_current_user

app = FastAPI(
    title="Order Service",
    description="Create orders, reserve inventory, and view order history",
    version="1.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE = os.path.join(os.path.dirname(__file__), "orders.db")
PRODUCT_SERVICE_URL = "http://127.0.0.1:8102"
INVENTORY_SERVICE_URL = "http://127.0.0.1:8103"


def get_connection():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with closing(get_connection()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                total_amount REAL NOT NULL CHECK(total_amount >= 0),
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                unit_price REAL NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                FOREIGN KEY(order_id) REFERENCES orders(id)
            )
        """)
        connection.commit()


initialize_database()


class OrderItemInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)


class OrderCreate(BaseModel):
    items: list[OrderItemInput] = Field(min_length=1, max_length=100)


@app.get("/")
def root():
    return {"service": "Order Service", "status": "running"}


@app.get("/health")
def health():
    return {"service": "order", "status": "healthy"}


def fetch_verified_products(items):
    verified_items = []
    try:
        with httpx.Client(timeout=5.0) as client:
            for item in items:
                response = client.get(f"{PRODUCT_SERVICE_URL}/products/{item.product_id}")
                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
                response.raise_for_status()
                product = response.json()
                if "name" not in product or "price" not in product:
                    raise HTTPException(status_code=502, detail="Product Service returned incomplete product data")
                price = float(product["price"])
                if price < 0:
                    raise HTTPException(status_code=502, detail="Product Service returned an invalid price")
                verified_items.append({
                    "product_id": item.product_id,
                    "product_name": str(product["name"]),
                    "unit_price": price,
                    "quantity": item.quantity,
                })
    except HTTPException:
        raise
    except (httpx.RequestError, httpx.HTTPStatusError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=503, detail="Could not verify products. Please try again later.")
    return verified_items


def reserve_inventory(items, authorization):
    reservation_items = [
        {"product_id": item["product_id"], "quantity": item["quantity"], "reason": "Order reservation"}
        for item in items
    ]
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(
                f"{INVENTORY_SERVICE_URL}/stock/reserve-batch",
                json={"items": reservation_items},
                headers={"Authorization": authorization},
            )
        if response.status_code == 409:
            try:
                detail = response.json().get("detail", "Insufficient stock")
            except ValueError:
                detail = "Insufficient stock"
            raise HTTPException(status_code=409, detail=detail)
        if response.status_code in (401, 403):
            raise HTTPException(status_code=response.status_code, detail="Inventory reservation was not authorized")
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except (httpx.RequestError, httpx.HTTPStatusError):
        raise HTTPException(status_code=503, detail="Could not reserve inventory. Please try again later.")


@app.post("/orders", status_code=201)
def create_order(
    request: OrderCreate,
    http_request: Request,
    user: dict = Depends(get_current_user),
):
    authorization = http_request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required for inventory reservation")

    verified_items = fetch_verified_products(request.items)
    total = round(sum(item["unit_price"] * item["quantity"] for item in verified_items), 2)
    order_number = "ORD-" + uuid.uuid4().hex[:12].upper()
    created_at = datetime.now(timezone.utc).isoformat()

    with closing(get_connection()) as connection:
        try:
            connection.execute("BEGIN")
            cursor = connection.execute(
                """INSERT INTO orders
                   (order_number, user_id, total_amount, status, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (order_number, user["user_id"], total, "Pending", created_at),
            )
            order_id = cursor.lastrowid
            for item in verified_items:
                connection.execute(
                    """INSERT INTO order_items
                       (order_id, product_id, product_name, unit_price, quantity)
                       VALUES (?, ?, ?, ?, ?)""",
                    (order_id, item["product_id"], item["product_name"], item["unit_price"], item["quantity"]),
                )
            reservation = reserve_inventory(verified_items, authorization)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        "message": "Order created and inventory reserved successfully",
        "order_id": order_id,
        "order_number": order_number,
        "user_id": user["user_id"],
        "total_amount": total,
        "status": "Pending",
        "created_at": created_at,
        "items": verified_items,
        "inventory_reservation": reservation,
    }


@app.get("/orders")
def list_orders(user: dict = Depends(get_current_user)):
    with closing(get_connection()) as connection:
        orders = connection.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user["user_id"],)
        ).fetchall()
        result = []
        for order in orders:
            items = connection.execute(
                """SELECT product_id, product_name, unit_price, quantity
                   FROM order_items WHERE order_id = ?""",
                (order["id"],),
            ).fetchall()
            result.append({**dict(order), "items": [dict(item) for item in items]})
    return {"count": len(result), "orders": result}


@app.get("/orders/{order_id}")
def get_order(order_id: int, user: dict = Depends(get_current_user)):
    with closing(get_connection()) as connection:
        if user.get("role") == "Admin":
            order = connection.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
        else:
            order = connection.execute(
                "SELECT * FROM orders WHERE id = ? AND user_id = ?",
                (order_id, user["user_id"]),
            ).fetchone()

        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")

        items = connection.execute(
            """SELECT product_id, product_name, unit_price, quantity
               FROM order_items WHERE order_id = ?""",
            (order_id,),
        ).fetchall()
    return {**dict(order), "items": [dict(item) for item in items]}


@app.post("/orders/{order_id}/confirm-payment")
def confirm_payment(order_id: int, user: dict = Depends(get_current_user)):
    """Confirm an order after a successful simulated payment."""
    with closing(get_connection()) as connection:
        order = connection.execute(
            "SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user["user_id"])
        ).fetchone()
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        if order["status"] == "Confirmed":
            return {"message": "Order was already confirmed", "order_id": order_id, "status": "Confirmed"}
        if order["status"] != "Pending":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot confirm payment for an order with status {order['status']}",
            )
        connection.execute("UPDATE orders SET status = 'Confirmed' WHERE id = ?", (order_id,))
        connection.commit()
    return {"message": "Order confirmed after successful payment", "order_id": order_id, "status": "Confirmed"}


@app.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: int,
    http_request: Request,
    user: dict = Depends(get_current_user),
):
    """Cancel an order and release reserved inventory exactly once."""
    authorization = http_request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required")

    with closing(get_connection()) as connection:
        if user.get("role") == "Admin":
            order = connection.execute(
                "SELECT * FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        else:
            order = connection.execute(
                "SELECT * FROM orders WHERE id = ? AND user_id = ?",
                (order_id, user["user_id"]),
            ).fetchone()

        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        if order["status"] == "Cancelled":
            return {
                "message": "Order is already cancelled",
                "order_id": order_id,
                "status": "Cancelled",
                "inventory_released": True,
            }
        if order["status"] not in ("Pending", "Confirmed"):
            raise HTTPException(
                status_code=409,
                detail=f"Order with status {order['status']} cannot be cancelled",
            )
        items = connection.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
            (order_id,),
        ).fetchall()

    if not items:
        raise HTTPException(status_code=409, detail="Order has no items to release")

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(
                f"{INVENTORY_SERVICE_URL}/stock/release-batch",
                json={
                    "order_id": order_id,
                    "items": [
                        {"product_id": item["product_id"], "quantity": item["quantity"]}
                        for item in items
                    ],
                },
                headers={"Authorization": authorization},
            )
            response.raise_for_status()
            release_result = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Inventory Service rejected stock release: {exc.response.text[:300]}",
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Inventory Service is unavailable; order was not cancelled")

    # Only mark the order cancelled after Inventory Service confirms (or confirms
    # a prior successful) release. If this update fails, retrying is safe because
    # Inventory Service records each order release idempotently.
    with closing(get_connection()) as connection:
        if user.get("role") == "Admin":
            connection.execute(
                "UPDATE orders SET status = 'Cancelled' WHERE id = ? AND status IN ('Pending', 'Confirmed')",
                (order_id,),
            )
            updated = connection.execute(
                "SELECT status FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        else:
            connection.execute(
                "UPDATE orders SET status = 'Cancelled' WHERE id = ? AND user_id = ? AND status IN ('Pending', 'Confirmed')",
                (order_id, user["user_id"]),
            )
            updated = connection.execute(
                "SELECT status FROM orders WHERE id = ? AND user_id = ?",
                (order_id, user["user_id"]),
            ).fetchone()

        connection.commit()

    if updated is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if updated["status"] != "Cancelled":
        raise HTTPException(status_code=409, detail=f"Order status changed to {updated['status']} during cancellation")

    return {
        "message": "Order cancelled and inventory released",
        "order_id": order_id,
        "status": "Cancelled",
        "inventory_release": release_result,
    }

