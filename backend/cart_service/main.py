import os
import sqlite3
from contextlib import closing

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth_service.security import get_current_user

app = FastAPI(
    title="Cart Service",
    description="Manage customer shopping carts",
    version="1.0.0",
)

DATABASE = os.path.join(os.path.dirname(__file__), "cart.db")


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(get_connection()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                unit_price REAL NOT NULL CHECK(unit_price >= 0),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                UNIQUE(user_id, product_id)
            )
        """)
        connection.commit()


initialize_database()


class AddToCartRequest(BaseModel):
    product_id: int = Field(gt=0)
    product_name: str = Field(min_length=2, max_length=150)
    unit_price: float = Field(ge=0, le=100000000)
    quantity: int = Field(gt=0, le=1000)


class UpdateCartRequest(BaseModel):
    quantity: int = Field(gt=0, le=1000)


@app.get("/")
def root():
    return {"service": "Cart Service", "status": "running"}


@app.get("/health")
def health():
    return {"service": "cart", "status": "healthy"}


@app.post("/cart/items", status_code=201)
def add_to_cart(
    request: AddToCartRequest,
    user: dict = Depends(get_current_user),
):
    with closing(get_connection()) as connection:
        existing = connection.execute(
            """
            SELECT id, quantity FROM cart_items
            WHERE user_id = ? AND product_id = ?
            """,
            (user["user_id"], request.product_id),
        ).fetchone()

        if existing:
            connection.execute(
                """
                UPDATE cart_items
                SET quantity = quantity + ?,
                    product_name = ?,
                    unit_price = ?
                WHERE id = ?
                """,
                (
                    request.quantity,
                    request.product_name.strip(),
                    request.unit_price,
                    existing["id"],
                ),
            )
        else:
            connection.execute(
                """
                INSERT INTO cart_items
                    (user_id, product_id, product_name, unit_price, quantity)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user["user_id"],
                    request.product_id,
                    request.product_name.strip(),
                    request.unit_price,
                    request.quantity,
                ),
            )
        connection.commit()

        row = connection.execute(
            """
            SELECT * FROM cart_items
            WHERE user_id = ? AND product_id = ?
            """,
            (user["user_id"], request.product_id),
        ).fetchone()

    return {"message": "Item added to cart", "item": dict(row)}


@app.get("/cart")
def get_cart(user: dict = Depends(get_current_user)):
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM cart_items WHERE user_id = ? ORDER BY id",
            (user["user_id"],),
        ).fetchall()

    items = [dict(row) for row in rows]
    total = round(sum(item["unit_price"] * item["quantity"] for item in items), 2)

    return {
        "user_id": user["user_id"],
        "items": items,
        "total_items": sum(item["quantity"] for item in items),
        "total_price": total,
    }


@app.put("/cart/items/{product_id}")
def update_cart_item(
    product_id: int,
    request: UpdateCartRequest,
    user: dict = Depends(get_current_user),
):
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            UPDATE cart_items SET quantity = ?
            WHERE user_id = ? AND product_id = ?
            """,
            (request.quantity, user["user_id"], product_id),
        )
        connection.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Cart item not found")

    return {"message": "Cart quantity updated", "product_id": product_id,
            "quantity": request.quantity}


@app.delete("/cart/items/{product_id}")
def remove_cart_item(
    product_id: int,
    user: dict = Depends(get_current_user),
):
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
            (user["user_id"], product_id),
        )
        connection.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Cart item not found")

    return {"message": "Item removed from cart", "product_id": product_id}
