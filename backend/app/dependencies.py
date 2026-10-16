
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.jwt_service import verify_access_token


# Extract HTTP Bearer credentials.
# auto_error=False lets us return a consistent 401.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AccessToken",
)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    # 1. Ensure a Bearer token was supplied.
    if credentials is None:
        raise authentication_error()

    # 2. Verify JWT and extract the subject UUID.
    try:
        user_id = verify_access_token(
            credentials.credentials
        )
    except (InvalidTokenError, ValueError):
        raise authentication_error() from None

    # 3. Retrieve the actual user from PostgreSQL.
    user = db.get(User, user_id)

    # 4. Reject tokens whose user no longer exists.
    if user is None:
        raise authentication_error()

    # 5. Return the authenticated SQLAlchemy user.
    return user


CurrentUser = Annotated[
    User,
    Depends(get_current_user),
]
