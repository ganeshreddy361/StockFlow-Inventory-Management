from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, timedelta, timezone
import os
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from passlib.context import CryptContext
from jose import jwt

app = FastAPI(
    title="Authentication Service",
    description="User registration and login for the Inventory and Order Management System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

DATABASE = os.path.join(os.path.dirname(__file__), "auth.db")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.environ["JWT_SECRET_KEY"])
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 30

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Customer',
                created_at TEXT NOT NULL
            )
        """)


initialize_database()


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=72)
    role: str = "Customer"


class LoginRequest(BaseModel):
    email: str
    password: str


def create_access_token(user_id: int, role: str):
    expires = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expires,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@app.get("/")
def root():
    return {"service": "Authentication Service", "status": "running"}


@app.get("/health")
def health():
    return {"service": "auth", "status": "healthy"}


@app.post("/register", status_code=201)
def register(request: RegisterRequest):
    email = request.email.strip().lower()

    # Public registration can only create Customer accounts.
    if request.role != "Customer":
        raise HTTPException(
            status_code=403,
            detail="Public registration is limited to Customer accounts",
        )

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Enter a valid email address")

    password_hash = password_context.hash(request.password)

    try:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users
                    (username, email, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request.username.strip(),
                    email,
                    password_hash,
                    "Customer",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Email is already registered")

    return {
        "message": "Registration successful",
        "user": {
            "id": user_id,
            "username": request.username.strip(),
            "email": email,
            "role": "Customer",
        },
    }


@app.post("/login")
def login(request: LoginRequest):
    email = request.email.strip().lower()

    with get_connection() as connection:
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not user or not password_context.verify(
        request.password, user["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user["id"], user["role"])

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
        },
    }


from backend.auth_service.security import get_current_user, require_roles
from fastapi import Depends


@app.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"message": "Token is valid", "user": user}


@app.get("/admin-test")
def admin_test(user: dict = Depends(require_roles("Admin"))):
    return {"message": "Admin access granted", "user": user}
