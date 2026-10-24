"""Password sign-in and the app's JWT authorization boundary."""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.session import require_frontend_origin, secure_cookies

router = APIRouter()
AUTH_COOKIE = "filevault_auth"
JWT_AGE = 60 * 60
password_hasher = PasswordHasher()
DUMMY_HASH = password_hasher.hash("not-a-user-password")


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


def jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters")
    return secret


def set_auth_cookie(response: Response, user: User) -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(user.id), "iss": "file-vault", "iat": now, "exp": now + timedelta(seconds=JWT_AGE)},
        jwt_secret(), algorithm="HS256",
    )
    response.set_cookie(AUTH_COOKIE, token, max_age=JWT_AGE, httponly=True,
                        secure=secure_cookies(), samesite="lax")


def optional_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(AUTH_COOKIE)
    if not token:
        return None
    try:
        claims = jwt.decode(token, jwt_secret(), algorithms=["HS256"], issuer="file-vault")
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        return None
    return db.get(User, user_id)


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    user = optional_user(request, db)
    if user is None:
        raise HTTPException(401, "Sign in first")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def user_json(user: User) -> dict[str, str]:
    return {"id": str(user.id), "email": user.email}


@router.post("/register", status_code=201)
def register(payload: Credentials, request: Request, response: Response,
             db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    require_frontend_origin(request)
    email = str(payload.email).lower()
    if email == os.getenv("STORAGE_GOOGLE_ACCOUNT_EMAIL", "").strip().lower():
        raise HTTPException(403, "The central storage account cannot register")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "Account already exists")
    user = User(email=email, password_hash=password_hasher.hash(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Account already exists") from None
    set_auth_cookie(response, user)
    return user_json(user)


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response,
          db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    require_frontend_origin(request)
    user = db.scalar(select(User).where(func.lower(User.email) == str(payload.email).lower()))
    stored_hash = user.password_hash if user and user.password_hash else DUMMY_HASH
    try:
        password_hasher.verify(stored_hash, payload.password)
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(401, "Invalid email or password") from None
    if user is None or not user.password_hash:
        raise HTTPException(401, "Invalid email or password")
    set_auth_cookie(response, user)
    return user_json(user)


@router.get("/me")
def me(user: CurrentUser) -> dict[str, str]:
    return user_json(user)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    require_frontend_origin(request)
    response.delete_cookie(AUTH_COOKIE, secure=secure_cookies(), httponly=True, samesite="lax")
    return {"signed_out": True}
