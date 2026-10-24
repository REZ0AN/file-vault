"""Local identities, Drive file references, and user Google credentials."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    storage_folder_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoredFile(Base):
    __tablename__ = "files"
    __table_args__ = (CheckConstraint("size_bytes >= 0", name="ck_files_size_nonnegative"),
                      Index("ix_files_user_id", "user_id"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    storage_drive_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    drive_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GoogleConnection(Base):
    __tablename__ = "google_connections"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_google_connections_user_id"),
        UniqueConstraint("google_subject", name="uq_google_connections_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    google_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    access_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    refresh_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    granted_scopes: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
