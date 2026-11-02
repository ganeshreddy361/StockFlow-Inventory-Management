from dotenv import load_dotenv

load_dotenv()
import os
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    os.environ["JWT_SECRET_KEY"],
)
ALGORITHM = "HS256"

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        expires = payload.get("exp")

        if not user_id or not role or not expires:
            raise HTTPException(
                status_code=401,
                detail="Invalid access token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if datetime.fromtimestamp(expires, timezone.utc) <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=401,
                detail="Access token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return {"user_id": int(user_id), "role": role}

    except (JWTError, ValueError, TypeError, OverflowError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_roles(*allowed_roles: str):
    def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this resource",
            )
        return user

    return role_checker
