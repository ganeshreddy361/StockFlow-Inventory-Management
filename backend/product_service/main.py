import os
import sqlite3
from contextlib import closing

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from backend.auth_service.security import get_current_user

app = FastAPI(
    title="Product Catalog Service",
    description="Create, browse, search, update, and delete products.",
    version="1.0.0",
)

DATABASE = os.path.join(os.path.dirname(__file__), "products.db")


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(get_connection()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                price REAL NOT NULL CHECK(price >= 0),
                stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()


initialize_database()


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=2000)
    category: str = Field(min_length=2, max_length=100)
    price: float = Field(ge=0, le=100000000)
    stock: int = Field(default=0, ge=0, le=100000000)


class ProductUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=2000)
    category: str = Field(min_length=2, max_length=100)
    price: float = Field(ge=0, le=100000000)
    stock: int = Field(ge=0, le=100000000)


def product_to_dict(row):
    return dict(row)


@app.get("/")
def root():
    return {"service": "Product Catalog Service", "status": "running"}


@app.get("/health")
def health():
    return {"service": "product", "status": "healthy"}


@app.post("/products", status_code=201)
def create_product(
    product: ProductCreate,
    user: dict = __import__("fastapi").Depends(get_current_user),
):
    if user["role"] not in ("Admin", "Inventory Manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO products (name, description, category, price, stock)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                product.name.strip(),
                product.description.strip(),
                product.category.strip(),
                product.price,
                product.stock,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

    return product_to_dict(row)


@app.get("/products")
def list_products(
    search: str | None = None,
    category: str | None = None,
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    sort_by: str = Query(default="name", pattern="^(name|price|created_at)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price cannot exceed max_price")

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if category:
        query += " AND category = ?"
        params.append(category)

    if min_price is not None:
        query += " AND price >= ?"
        params.append(min_price)

    if max_price is not None:
        query += " AND price <= ?"
        params.append(max_price)

    query += f" ORDER BY {sort_by} {order.upper()} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with closing(get_connection()) as connection:
        rows = connection.execute(query, params).fetchall()

    return {
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "products": [product_to_dict(row) for row in rows],
    }


@app.get("/products/{product_id}")
def get_product(product_id: int):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return product_to_dict(row)


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    product: ProductUpdate,
    user: dict = __import__("fastapi").Depends(get_current_user),
):
    if user["role"] not in ("Admin", "Inventory Manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    with closing(get_connection()) as connection:
        existing = connection.execute(
            "SELECT id FROM products WHERE id = ?", (product_id,)
        ).fetchone()

        if existing is None:
            raise HTTPException(status_code=404, detail="Product not found")

        connection.execute(
            """
            UPDATE products
            SET name = ?, description = ?, category = ?, price = ?, stock = ?
            WHERE id = ?
            """,
            (
                product.name.strip(),
                product.description.strip(),
                product.category.strip(),
                product.price,
                product.stock,
                product_id,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    return product_to_dict(row)


@app.delete("/products/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    user: dict = __import__("fastapi").Depends(get_current_user),
):
    if user["role"] != "Admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "DELETE FROM products WHERE id = ?", (product_id,)
        )
        connection.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Product not found")

    return None
