
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from jwt import InvalidTokenError


# 1. Load backend environment variables
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


# 2. JWT configuration
JWT_SECRET_HEX = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_HEX:
    raise RuntimeError("JWT_SECRET_KEY is not configured")

try:
    JWT_SECRET = bytes.fromhex(JWT_SECRET_HEX)
except ValueError as exc:
    raise RuntimeError(
        "JWT_SECRET_KEY must be hexadecimal"
    ) from exc

if len(JWT_SECRET) != 32:
    raise RuntimeError(
        "JWT_SECRET_KEY must contain exactly 32 random bytes"
    )


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

JWT_ISSUER = "file-vault-api"
JWT_AUDIENCE = "file-vault-client"


# 3. Create an access token
def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),
        "token_type": "access",
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=ALGORITHM,
    )


# 4. Validate an access token
def verify_access_token(token: str) -> uuid.UUID:
    payload = jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        options={
            "require": [
                "sub",
                "iat",
                "nbf",
                "exp",
                "iss",
                "aud",
                "jti",
                "token_type",
            ]
        },
    )

    if payload.get("token_type") != "access":
        raise InvalidTokenError("Invalid token type")

    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidTokenError(
            "Invalid subject identifier"
        ) from exc
