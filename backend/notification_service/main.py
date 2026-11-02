import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth_service.security import get_current_user

app = FastAPI(
    title="Notification Service",
    description="Record order notifications and low-stock alerts",
    version="1.1.0",
)

DATABASE = os.path.join(os.path.dirname(__file__), "notifications.db")


def get_connection():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with closing(get_connection()) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                event_type TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        connection.commit()


initialize_database()


class NotificationCreate(BaseModel):
    user_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=150)
    message: str = Field(min_length=2, max_length=1000)
    event_type: str = Field(min_length=2, max_length=80)


class UserNotificationCreate(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    message: str = Field(min_length=2, max_length=1000)
    event_type: str = Field(min_length=2, max_length=80)


def insert_notification(user_id, title, message, event_type):
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """INSERT INTO notifications
               (user_id, title, message, event_type, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, title.strip(), message.strip(), event_type.strip(), created_at),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM notifications WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


@app.get("/")
def root():
    return {"service": "Notification Service", "status": "running"}


@app.get("/health")
def health():
    return {"service": "notification", "status": "healthy"}


@app.post("/notifications", status_code=201)
def create_notification(
    request: NotificationCreate,
    user: dict = Depends(get_current_user),
):
    if user["role"] not in ("Admin", "Inventory Manager"):
        raise HTTPException(
            status_code=403,
            detail="Only authorized staff can create notifications using this endpoint",
        )
    notification = insert_notification(
        request.user_id, request.title, request.message, request.event_type
    )
    return {"message": "Notification created", "notification": notification}


@app.post("/notifications/events", status_code=201)
def create_user_event(
    request: UserNotificationCreate,
    user: dict = Depends(get_current_user),
):
    """Allow an authenticated user/service flow to create a notification only for that user."""
    notification = insert_notification(
        user["user_id"], request.title, request.message, request.event_type
    )
    return {"message": "Notification created", "notification": notification}


@app.get("/notifications")
def list_notifications(user: dict = Depends(get_current_user)):
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """SELECT * FROM notifications
               WHERE user_id = ?
               ORDER BY id DESC""",
            (user["user_id"],),
        ).fetchall()
    return {"count": len(rows), "notifications": [dict(row) for row in rows]}


@app.patch("/notifications/{notification_id}/read")
def mark_as_read(
    notification_id: int,
    user: dict = Depends(get_current_user),
):
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """UPDATE notifications SET is_read = 1
               WHERE id = ? AND user_id = ?""",
            (notification_id, user["user_id"]),
        )
        connection.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {
        "message": "Notification marked as read",
        "notification_id": notification_id,
    }
