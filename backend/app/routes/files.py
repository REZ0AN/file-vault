
import io
import re
import unicodedata
import zipfile
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File as UploadField,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import CurrentUser
from app.models.file import File as StoredFile
from app.schemas.file import (
    FileMetadataResponse,
    FileUploadResponse,
)


router = APIRouter(
    prefix="/files",
    tags=["Files"],
)

MAX_FILE_SIZE = 5 * 1024 * 1024

ALLOWED_FILE_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument."
        "presentationml.presentation"
    ),
}


# ---------------------------------------------------
# Filename and file validation
# ---------------------------------------------------

def sanitize_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required",
        )

    name = unicodedata.normalize("NFKC", filename)
    name = name.replace("\\", "/")
    name = PurePosixPath(name).name

    name = re.sub(r"[^\w.\- ]", "_", name)
    name = name.strip(" .")

    if not name or name in {".", ".."}:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename",
        )

    if len(name.encode("utf-8")) > 255:
        raise HTTPException(
            status_code=400,
            detail="Filename is too long",
        )

    return name


def validate_file(
    filename: str,
    content_type: str | None,
    content: bytes,
) -> str:
    extension = PurePosixPath(filename).suffix.lower()

    expected_mime = ALLOWED_FILE_TYPES.get(extension)

    if expected_mime is None:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file extension",
        )

    if content_type != expected_mime:
        raise HTTPException(
            status_code=415,
            detail="File MIME type does not match extension",
        )

    if extension == ".pdf":
        valid = content.startswith(b"%PDF-")

    elif extension == ".png":
        valid = content.startswith(
            b"\x89PNG\r\n\x1a\n"
        )

    elif extension in {".jpg", ".jpeg"}:
        valid = (
            content.startswith(b"\xff\xd8")
            and content.endswith(b"\xff\xd9")
        )

    elif extension in {".docx", ".pptx"}:
        valid = False

        try:
            with zipfile.ZipFile(
                io.BytesIO(content)
            ) as archive:
                names = set(archive.namelist())

                required = {"[Content_Types].xml"}

                if extension == ".docx":
                    required.add("word/document.xml")
                else:
                    required.add("ppt/presentation.xml")

                valid = required.issubset(names)

        except (zipfile.BadZipFile, OSError):
            valid = False

    else:
        valid = False

    if not valid:
        raise HTTPException(
            status_code=415,
            detail="File content does not match its type",
        )

    return expected_mime


# ---------------------------------------------------
# Upload a file
# POST /api/v1/files
# ---------------------------------------------------

@router.post(
    "",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_file(
    current_user: CurrentUser,
    file: UploadFile = UploadField(...),
    db: Session = Depends(get_db),
):
    safe_filename = sanitize_filename(file.filename)

    extension = PurePosixPath(
        safe_filename
    ).suffix.lower()

    expected_mime = ALLOWED_FILE_TYPES.get(extension)

    if expected_mime is None:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file extension",
        )

    if file.content_type != expected_mime:
        raise HTTPException(
            status_code=415,
            detail="File MIME type does not match extension",
        )

    try:
        content = file.file.read(MAX_FILE_SIZE + 1)
    finally:
        file.file.close()

    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=400,
            detail="Empty files are not allowed",
        )

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File exceeds the 5 MiB limit",
        )

    validated_mime = validate_file(
        safe_filename,
        file.content_type,
        content,
    )

    stored_file = StoredFile(
        user_id=current_user.id,
        filename=safe_filename,
        mime_type=validated_mime,
        size_bytes=file_size,
        content=content,
    )

    db.add(stored_file)

    try:
        db.commit()
        db.refresh(
            stored_file,
            attribute_names=["created_at"],
        )
    except Exception:
        db.rollback()
        raise

    return FileUploadResponse.model_validate(
        stored_file
    )


# ---------------------------------------------------
# List authenticated user's files
# GET /api/v1/files
# ---------------------------------------------------

@router.get(
    "",
    response_model=list[FileMetadataResponse],
)
def list_files(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    statement = (
        select(
            StoredFile.id,
            StoredFile.filename,
            StoredFile.mime_type,
            StoredFile.size_bytes,
            StoredFile.created_at,
        )
        .where(
            StoredFile.user_id == current_user.id
        )
        .order_by(
            StoredFile.created_at.desc(),
            StoredFile.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(statement).mappings().all()

    return [
        FileMetadataResponse.model_validate(
            dict(row)
        )
        for row in rows
    ]


# ---------------------------------------------------
# Download an owned file
# GET /api/v1/files/{file_id}/download
# ---------------------------------------------------

@router.get(
    "/{file_id}/download",
    response_class=Response,
)
def download_file(
    file_id: UUID,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    statement = select(StoredFile).where(
        StoredFile.id == file_id,
        StoredFile.user_id == current_user.id,
    )

    stored_file = db.scalar(statement)

    if stored_file is None:
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    # BYTEA was deferred, so accessing it now
    # loads the actual binary into memory.
    content = stored_file.content

    # Safe ASCII fallback for Content-Disposition.
    ascii_filename = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        stored_file.filename,
    ) or "download"

    # RFC 5987-compatible UTF-8 filename.
    encoded_filename = quote(
        stored_file.filename,
        safe="",
    )

    disposition = (
        f'attachment; filename="{ascii_filename}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )

    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
