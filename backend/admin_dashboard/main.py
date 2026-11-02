import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.auth_service.security import get_current_user

app = FastAPI(
    title="Admin Dashboard Service",
    description="Read-only administrator dashboard for products, orders, inventory, and sales",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

BASE_DIR = Path(__file__).resolve().parents[1]
PRODUCTS_DB = BASE_DIR / "product_service" / "products.db"
ORDERS_DB = BASE_DIR / "order_service" / "orders.db"
INVENTORY_DB = BASE_DIR / "inventory_service" / "inventory.db"
PAYMENTS_DB = BASE_DIR / "payment_service" / "payments.db"
AUTH_DB = BASE_DIR / "auth_service" / "auth.db"


def connect_read_only(database_path: Path):
    """Open an existing SQLite database without allowing writes."""
    if not database_path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Required database is missing: {database_path.name}",
        )

    connection = sqlite3.connect(
        f"file:{database_path.resolve()}?mode=ro",
        uri=True,
        timeout=5,
    )
    connection.row_factory = sqlite3.Row
    return connection


def admin_only(user: dict = Depends(get_current_user)):
    if user.get("role") != "Admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access dashboard data",
        )
    return user


@app.get("/")
def root():
    return {"service": "Admin Dashboard Service", "status": "running"}


@app.get("/health")
def health():
    return {"service": "admin-dashboard", "status": "healthy"}


@app.get("/dashboard/summary")
def dashboard_summary(user: dict = Depends(admin_only)):
    with closing(connect_read_only(PRODUCTS_DB)) as connection:
        product_count = connection.execute(
            "SELECT COUNT(*) AS count FROM products"
        ).fetchone()["count"]
        catalog_value = connection.execute(
            "SELECT COALESCE(SUM(price * stock), 0) AS value FROM products"
        ).fetchone()["value"]

    with closing(connect_read_only(ORDERS_DB)) as connection:
        order_count = connection.execute(
            "SELECT COUNT(*) AS count FROM orders"
        ).fetchone()["count"]
        order_status_rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM orders GROUP BY status"
        ).fetchall()
        order_status_counts = {
            row["status"]: row["count"] for row in order_status_rows
        }

    with closing(connect_read_only(INVENTORY_DB)) as connection:
        inventory_row = connection.execute(
            """
            SELECT
                COUNT(*) AS tracked_products,
                COALESCE(SUM(quantity), 0) AS total_units,
                COALESCE(SUM(CASE WHEN quantity <= 5 THEN 1 ELSE 0 END), 0)
                    AS low_stock_products,
                COALESCE(SUM(CASE WHEN quantity = 0 THEN 1 ELSE 0 END), 0)
                    AS out_of_stock_products
            FROM inventory
            """
        ).fetchone()

    with closing(connect_read_only(PAYMENTS_DB)) as connection:
        payment_row = connection.execute(
            """
            SELECT
                COUNT(*) AS successful_payment_count,
                COALESCE(SUM(amount), 0) AS successful_payment_amount
            FROM payments
            WHERE LOWER(status) = 'success'
            """
        ).fetchone()

    return {
        "products": {
            "total": product_count,
            "catalog_value_using_product_stock": round(float(catalog_value), 2),
        },
        "orders": {
            "total": order_count,
            "by_status": order_status_counts,
        },
        "inventory": {
            "tracked_products": inventory_row["tracked_products"],
            "total_units_available": inventory_row["total_units"],
            "low_stock_products_threshold_5_or_less": inventory_row["low_stock_products"],
            "out_of_stock_products": inventory_row["out_of_stock_products"],
        },
        "sales": {
            "successful_payment_count": payment_row["successful_payment_count"],
            "successful_payment_revenue": round(
                float(payment_row["successful_payment_amount"]), 2
            ),
            "currency": "INR",
        },
        "note": (
            "Available stock is read from the Inventory Service database. "
            "Catalog value uses the product table's stock field and is shown "
            "separately because product stock may differ from inventory quantities."
        ),
    }


@app.get("/dashboard/products")
def dashboard_products(
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(admin_only),
):
    with closing(connect_read_only(PRODUCTS_DB)) as connection:
        rows = connection.execute(
            """
            SELECT id, name, description, category, price, stock, created_at
            FROM products
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return {"count": len(rows), "products": [dict(row) for row in rows]}


@app.get("/dashboard/orders")
def dashboard_orders(
    status: Optional[str] = Query(default=None, min_length=1, max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(admin_only),
):
    with closing(connect_read_only(ORDERS_DB)) as connection:
        if status:
            rows = connection.execute(
                """
                SELECT o.id, o.order_number, o.user_id, o.total_amount,
                       o.status, o.created_at,
                       COUNT(oi.id) AS item_line_count,
                       COALESCE(SUM(oi.quantity), 0) AS total_item_quantity
                FROM orders o
                LEFT JOIN order_items oi ON oi.order_id = o.id
                WHERE LOWER(o.status) = LOWER(?)
                GROUP BY o.id
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (status.strip(), limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT o.id, o.order_number, o.user_id, o.total_amount,
                       o.status, o.created_at,
                       COUNT(oi.id) AS item_line_count,
                       COALESCE(SUM(oi.quantity), 0) AS total_item_quantity
                FROM orders o
                LEFT JOIN order_items oi ON oi.order_id = o.id
                GROUP BY o.id
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    return {"count": len(rows), "orders": [dict(row) for row in rows]}


@app.get("/dashboard/inventory")
def dashboard_inventory(
    low_stock_threshold: int = Query(default=5, ge=0, le=1000000),
    low_stock_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(admin_only),
):
    with closing(connect_read_only(PRODUCTS_DB)) as products_connection:
        product_rows = products_connection.execute(
            "SELECT id, name, category, price FROM products"
        ).fetchall()
    products = {row["id"]: dict(row) for row in product_rows}

    with closing(connect_read_only(INVENTORY_DB)) as connection:
        if low_stock_only:
            rows = connection.execute(
                """
                SELECT product_id, quantity, updated_at
                FROM inventory
                WHERE quantity <= ?
                ORDER BY quantity ASC, product_id ASC
                LIMIT ?
                """,
                (low_stock_threshold, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT product_id, quantity, updated_at
                FROM inventory
                ORDER BY quantity ASC, product_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        product = products.get(item["product_id"], {})
        item["product_name"] = product.get("name", "Unknown product")
        item["category"] = product.get("category")
        item["price"] = product.get("price")
        item["low_stock"] = item["quantity"] <= low_stock_threshold
        result.append(item)

    return {
        "count": len(result),
        "low_stock_threshold": low_stock_threshold,
        "inventory": result,
    }



@app.get("/dashboard/sales")
def dashboard_sales(
    from_date: Optional[str] = Query(default=None, pattern=r"^\\d{4}-\\d{2}-\\d{2}$"),
    to_date: Optional[str] = Query(default=None, pattern=r"^\\d{4}-\\d{2}-\\d{2}$"),
    user: dict = Depends(admin_only),
):
    from datetime import date

    try:
        start_date = date.fromisoformat(from_date) if from_date else None
        end_date = date.fromisoformat(to_date) if to_date else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be valid YYYY-MM-DD dates.")

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date.")

    conditions = []
    parameters = []

    if from_date:
        conditions.append("substr(created_at, 1, 10) >= ?")
        parameters.append(from_date)

    if to_date:
        conditions.append("substr(created_at, 1, 10) <= ?")
        parameters.append(to_date)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    with closing(connect_read_only(PAYMENTS_DB)) as connection:
        by_status_rows = connection.execute(
            f"""
            SELECT status, COUNT(*) AS payment_count,
                   COALESCE(SUM(amount), 0) AS total_amount
            FROM payments
            {where_clause}
            GROUP BY status
            ORDER BY status
            """,
            parameters,
        ).fetchall()

        successful_by_day_rows = connection.execute(
            f"""
            SELECT substr(created_at, 1, 10) AS date,
                   COUNT(*) AS payment_count,
                   COALESCE(SUM(amount), 0) AS revenue
            FROM payments
            {where_clause + ' AND ' if where_clause else 'WHERE '}
                LOWER(status) = 'success'
            GROUP BY substr(created_at, 1, 10)
            ORDER BY date DESC
            """,
            parameters,
        ).fetchall()

    successful_count = sum(
        row["payment_count"]
        for row in by_status_rows
        if str(row["status"]).lower() == "success"
    )
    successful_revenue = sum(
        float(row["total_amount"] or 0)
        for row in by_status_rows
        if str(row["status"]).lower() == "success"
    )

    return {
        "payments_by_status": [
            {
                "status": row["status"],
                "payment_count": row["payment_count"],
                "total_amount": round(float(row["total_amount"]), 2),
            }
            for row in by_status_rows
        ],
        "successful_sales_by_day": [
            {
                "date": row["date"],
                "payment_count": row["payment_count"],
                "revenue": round(float(row["revenue"]), 2),
            }
            for row in successful_by_day_rows
        ],
        "successful_payment_count": successful_count,
        "successful_payment_revenue": round(successful_revenue, 2),
        "from_date": from_date,
        "to_date": to_date,
        "currency": "INR",
        "note": (
            "Revenue is calculated from successful payment records. "
            "Refunds are not deducted because a refund workflow has not been implemented."
        ),
    }

@app.get("/dashboard/customers")
def dashboard_customers(
    search: Optional[str] = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(admin_only),
):
    with closing(connect_read_only(AUTH_DB)) as users_connection:
        if search and search.strip():
            term = f"%{search.strip()}%"
            users = users_connection.execute(
                """
                SELECT id, username, email, created_at
                FROM users
                WHERE role = 'Customer'
                  AND (username LIKE ? OR email LIKE ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (term, term, limit),
            ).fetchall()
        else:
            users = users_connection.execute(
                """
                SELECT id, username, email, created_at
                FROM users
                WHERE role = 'Customer'
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    customers = [dict(row) for row in users]
    customer_ids = [customer["id"] for customer in customers]

    if customer_ids:
        placeholders = ",".join("?" for _ in customer_ids)

        with closing(connect_read_only(ORDERS_DB)) as orders_connection:
            summaries = orders_connection.execute(
                f"""
                SELECT user_id,
                       COUNT(*) AS total_orders,
                       SUM(CASE WHEN status = 'Confirmed' THEN 1 ELSE 0 END)
                           AS confirmed_orders,
                       SUM(CASE WHEN status = 'Confirmed'
                           THEN total_amount ELSE 0 END)
                           AS confirmed_purchase_total
                FROM orders
                WHERE user_id IN ({placeholders})
                GROUP BY user_id
                """,
                customer_ids,
            ).fetchall()

        summary_by_user = {
            row["user_id"]: dict(row) for row in summaries
        }

        for customer in customers:
            summary = summary_by_user.get(customer["id"], {})
            customer["total_orders"] = summary.get("total_orders", 0)
            customer["confirmed_orders"] = summary.get("confirmed_orders", 0)
            customer["confirmed_purchase_total"] = round(
                float(summary.get("confirmed_purchase_total") or 0), 2
            )
    else:
        for customer in customers:
            customer["total_orders"] = 0
            customer["confirmed_orders"] = 0
            customer["confirmed_purchase_total"] = 0

    return {"count": len(customers), "customers": customers}


@app.get("/dashboard/customers/{customer_id}/orders")
def dashboard_customer_orders(
    customer_id: int,
    user: dict = Depends(admin_only),
):
    with closing(connect_read_only(AUTH_DB)) as users_connection:
        customer = users_connection.execute(
            """
            SELECT id, username, email, created_at
            FROM users
            WHERE id = ? AND role = 'Customer'
            """,
            (customer_id,),
        ).fetchone()

    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    with closing(connect_read_only(ORDERS_DB)) as orders_connection:
        orders = orders_connection.execute(
            """
            SELECT id, order_number, user_id, total_amount, status, created_at
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (customer_id,),
        ).fetchall()

        result = []
        for order in orders:
            items = orders_connection.execute(
                """
                SELECT product_id, product_name, unit_price, quantity
                FROM order_items
                WHERE order_id = ?
                """,
                (order["id"],),
            ).fetchall()

            result.append({
                **dict(order),
                "items": [dict(item) for item in items],
            })

    return {
        "customer": dict(customer),
        "count": len(result),
        "orders": result,
    }
