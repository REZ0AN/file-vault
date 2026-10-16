
from app.dependencies import CurrentUser, get_current_user
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    UserLogin,
    UserRegister,
    UserResponse,
    TokenResponse,
)
from app.services.security import (
    hash_password,
    verify_password,
)
from app.services.jwt_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ---------------------------------------------------
# Register a new user (existing functionality)
# ---------------------------------------------------

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    payload: UserRegister,
    db: Session = Depends(get_db),
):
    existing_user = db.scalar(
        select(User.id).where(
            User.email == payload.email
        )
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    hashed_password = hash_password(payload.password)

    user = User(
        email=payload.email,
        password_hash=hashed_password,
    )

    db.add(user)

    try:
        db.commit()

    except IntegrityError as exc:
        db.rollback()

        sqlstate = getattr(exc.orig, "sqlstate", None)
        constraint = getattr(
            getattr(exc.orig, "diag", None),
            "constraint_name",
            None,
        )

        if (
            sqlstate == "23505"
            and constraint == "users_email_key"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from exc

        raise

    db.refresh(user)

    return user


# ---------------------------------------------------
# Login and issue JWT
# ---------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login_user(
    payload: UserLogin,
    db: Session = Depends(get_db),
):
    # 1. Find the user by normalized email
    user = db.scalar(
        select(User).where(
            User.email == payload.email
        )
    )

    # 2. Verify credentials
    if user is None:
        # Perform dummy verification to reduce
        # timing differences for unknown emails.
        verify_password(
            payload.password,
            DUMMY_PASSWORD_HASH,
        )

        raise invalid_credentials()

    if not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise invalid_credentials()

    # 3. Issue a signed JWT
    access_token = create_access_token(user.id)

    # 4. Serialize the response
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

# ---------------------------------------------------
# Current authenticated user
# GET /api/v1/auth/me
# ---------------------------------------------------

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def get_my_profile(
    current_user: CurrentUser,
):
    return current_user

# Precomputed Argon2id hash for missing-user checks.
# This represents a random dummy password.
# It is not an application account credential.
DUMMY_PASSWORD_HASH = (
"$argon2id$v=19$m=65536,t=3,p=4$"
"4EAiWCRuDPCpCSM2+UCGVg$"
"0vvYpDilN0SVF7sUKB0uU7vPcSt8nDQffBdpR9mbuUk"
)


def invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )
