
"""
SQLAlchemy model for Google OAuth connections.

A connection belongs to a File Vault user and
contains encrypted Google OAuth tokens.

Important:
- Never store plaintext Google tokens.
- Encryption happens in a separate service.
- This model does not implement OAuth flows.
"""

import uuid

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# Use the same Base import as app/models/user.py.
from app.database import Base


class GoogleConnection(Base):
    __tablename__ = "google_connections"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_google_connections_user_id",
        ),
    )

    # -------------------------------------------
    # Primary key
    # -------------------------------------------

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # -------------------------------------------
    # File Vault user ownership
    # -------------------------------------------

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # -------------------------------------------
    # Google account identity
    # -------------------------------------------

    # Stable Google account identifier.
    # Nullable until an identity-enabled OAuth
    # flow supplies a verified Google subject.
    google_subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Display information, not an ownership key.
    google_email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )

    # -------------------------------------------
    # Encrypted Google OAuth tokens
    # -------------------------------------------

    # Fernet-encrypted bytes, not raw tokens.
    # Deferred so routine metadata queries
    # do not load sensitive token columns.
    access_token_ciphertext: Mapped[bytes | None] = (
        mapped_column(
            LargeBinary,
            nullable=True,
            deferred=True,
        
        )
    )

    refresh_token_ciphertext: Mapped[bytes | None] = (
        mapped_column(
            LargeBinary,
            nullable=True,
            deferred=True,

        )
    )

    # -------------------------------------------
    # OAuth token metadata
    # -------------------------------------------

    # Space-separated scope URLs returned by Google.
    granted_scopes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    # Google access token expiry, stored in UTC.
    access_token_expires_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -------------------------------------------
    # Audit timestamps
    # -------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # -------------------------------------------
    # Safe debugging representation
    # -------------------------------------------

    def __repr__(self) -> str:
        return (
            "GoogleConnection("
            f"id={self.id!r}, "
            f"user_id={self.user_id!r}"
            ")"
        )
