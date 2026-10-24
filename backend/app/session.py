"""Encrypted OAuth state cookies and write-request origin checks."""

import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, Response

STATE_COOKIE = "drive_oauth_state"
STATE_AGE = 60 * 10
STATE_PATH = "/api/v1/google/callback"


def cipher() -> Fernet:
    key = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("GOOGLE_TOKEN_ENCRYPTION_KEY is required")
    return Fernet(key.encode())


def secure_cookies() -> bool:
    return os.getenv("GOOGLE_REDIRECT_URI", "").startswith("https://")


def write_cookie(response: Response, name: str, data: dict[str, Any], age: int, path: str = "/") -> None:
    value = cipher().encrypt(json.dumps(data).encode()).decode()
    response.set_cookie(name, value, max_age=age, path=path, httponly=True,
                        secure=secure_cookies(), samesite="lax")


def read_cookie(request: Request, name: str, age: int) -> dict[str, Any] | None:
    value = request.cookies.get(name)
    if not value:
        return None
    try:
        data = json.loads(cipher().decrypt(value.encode(), ttl=age))
        return data if isinstance(data, dict) else None
    except (InvalidToken, ValueError, TypeError):
        return None


def require_frontend_origin(request: Request) -> None:
    frontend = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")
    backend = str(request.base_url).rstrip("/")
    if request.headers.get("origin") not in (frontend, backend):
        raise HTTPException(403, "Invalid request origin")
