
from datetime import datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


# 1. Registration request
class UserRegister(BaseModel):
    """Request schema for registering a new user."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
        repr=False,
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 256:
            raise ValueError(
                "Password must not exceed 256 UTF-8 bytes"
            )

        if not value.strip():
            raise ValueError(
                "Password cannot be only whitespace"
            )

        return value


# 2. Registration response
class UserResponse(BaseModel):
    """Public user data returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    created_at: datetime


# 3. Login request
class UserLogin(BaseModel):
    """Credentials supplied during login."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
        repr=False,
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 256:
            raise ValueError(
                "Password must not exceed 256 UTF-8 bytes"
            )

        return value


# 4. JWT login response
class TokenResponse(BaseModel):
    """Access token returned after successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900
