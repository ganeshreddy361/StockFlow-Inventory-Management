import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from backend.auth_service.security import get_current_user

app = FastAPI(
    title="Payment Service",
    description="Simulated payment processing for development and testing",
    version="1.1.0",
)

DATABASE = os.path.join(os.path.dirname(__file__), "payments.db")
ORDER_SERVICE_URL = "http://127.0.0.1:8105"
NOTIFICATION_SERVICE_URL = "http://127.0.0.1:8107"
PAYMENT_STATUSES = {"success", "failure", "cancelled"}


def get_connection():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(get_connection()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_ref TEXT NOT NULL UNIQUE,
                order_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        connection.commit()


initialize_database()


class PaymentRequest(BaseModel):
    order_id: int = Field(gt=0)
    amount: float = Field(gt=0, le=100000000)
    outcome: str = Field(pattern="^(success|failure|cancelled)$")


@app.get("/")
def root():
    return {"service": "Payment Service", "status": "running"}


@app.get("/health")
def health():
    return {"service": "payment", "status": "healthy"}


def notify_user(authorization, title, message, event_type):
    """Best-effort notification; payment processing remains recorded if notification fails."""
    try:
        with httpx.Client(timeout=4.0) as client:
            response = client.post(
                f"{NOTIFICATION_SERVICE_URL}/notifications/events",
                json={"title": title, "message": message, "event_type": event_type},
                headers={"Authorization": authorization},
            )
        response.raise_for_status()
        return {"sent": True, "notification": response.json()}
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        return {"sent": False, "message": "Notification service could not be reached"}


@app.post("/payments", status_code=201)
def create_payment(
    request: PaymentRequest,
    http_request: Request,
    user: dict = Depends(get_current_user),
):
    authorization = http_request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required")

    # Verify order ownership and authoritative total before recording payment.
    try:
        with httpx.Client(timeout=5.0) as client:
            order_response = client.get(
                f"{ORDER_SERVICE_URL}/orders/{request.order_id}",
                headers={"Authorization": authorization},
            )
        if order_response.status_code == 404:
            raise HTTPException(status_code=404, detail="Order not found for this user")
        if order_response.status_code in (401, 403):
            raise HTTPException(status_code=order_response.status_code, detail="Order verification was not authorized")
        order_response.raise_for_status()
        order = order_response.json()
    except HTTPException:
        raise
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        raise HTTPException(status_code=503, detail="Could not verify the order. Please try again later.")

    expected_amount = round(float(order["total_amount"]), 2)
    submitted_amount = round(float(request.amount), 2)
    if abs(expected_amount - submitted_amount) > 0.009:
        raise HTTPException(
            status_code=400,
            detail={"message": "Payment amount does not match the order total", "expected_amount": expected_amount},
        )
    if order["status"] != "Pending":
        raise HTTPException(
            status_code=409,
            detail=f"Payment can only be processed for Pending orders; current status is {order['status']}",
        )

    transaction_ref = "TXN-" + uuid.uuid4().hex[:12].upper()
    created_at = datetime.now(timezone.utc).isoformat()

    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """INSERT INTO payments
               (transaction_ref, order_id, user_id, amount, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (transaction_ref, request.order_id, user["user_id"], submitted_amount, request.outcome, created_at),
        )
        connection.commit()
        payment_id = cursor.lastrowid

    order_update = None
    if request.outcome == "success":
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.post(
                    f"{ORDER_SERVICE_URL}/orders/{request.order_id}/confirm-payment",
                    headers={"Authorization": authorization},
                )
            if response.status_code in (401, 403, 404, 409):
                # Payment is recorded, but report that the order transition did not complete.
                order_update = {"updated": False, "detail": response.text}
            else:
                response.raise_for_status()
                order_update = {"updated": True, "order": response.json()}
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
            order_update = {"updated": False, "detail": "Order service could not be reached"}

    if request.outcome == "success" and order_update and order_update.get("updated"):
        notification = notify_user(
            authorization,
            "Order confirmed",
            f"Payment successful for order #{request.order_id}. Your order is confirmed.",
            "payment_success",
        )
    elif request.outcome == "failure":
        notification = notify_user(
            authorization,
            "Payment failed",
            f"Payment failed for order #{request.order_id}. You can try again while the order remains pending.",
            "payment_failure",
        )
    elif request.outcome == "cancelled":
        notification = notify_user(
            authorization,
            "Payment cancelled",
            f"Payment was cancelled for order #{request.order_id}.",
            "payment_cancelled",
        )
    elif request.outcome == "success":
        notification = {"sent": False, "message": "Order confirmation did not complete; notification was not sent"}
    else:
        notification = {"sent": False, "message": "No notification was requested"}

    return {
        "message": "Simulated payment processed",
        "payment_id": payment_id,
        "transaction_ref": transaction_ref,
        "order_id": request.order_id,
        "amount": submitted_amount,
        "status": request.outcome,
        "created_at": created_at,
        "order_update": order_update,
        "notification_result": notification,
    }


@app.get("/payments")
def list_payments(user: dict = Depends(get_current_user)):
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC",
            (user["user_id"],),
        ).fetchall()
    return {"count": len(rows), "payments": [dict(row) for row in rows]}


@app.get("/payments/{payment_id}")
def get_payment(payment_id: int, user: dict = Depends(get_current_user)):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM payments WHERE id = ? AND user_id = ?",
            (payment_id, user["user_id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return dict(row)
