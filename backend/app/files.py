"""Owner-checked file metadata backed by central Drive storage."""

import uuid
from pathlib import PurePath
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.database import get_db
from app.google import GMAIL_SCOPE, access_token, create_gmail_draft, upload_bytes
from app.models import StoredFile, User
from app.preview import preview_response
from app.session import require_frontend_origin
from app.storage import create_user_folder, read_storage_file, root_folder_id, storage_access_token

router = APIRouter()
MAX_FILE_SIZE = 5 * 1024 * 1024


class DraftRequest(BaseModel):
    email: EmailStr


def file_json(file: StoredFile) -> dict:
    return {
        "id": str(file.id), "filename": file.filename,
        "mime_type": file.mime_type, "size_bytes": file.size_bytes,
        "drive_file_id": file.drive_file_id,
        "created_at": file.created_at.isoformat(),
    }


def owned_file(db: Session, user_id: uuid.UUID, file_id: uuid.UUID, *, lock: bool = False) -> StoredFile:
    query = select(StoredFile).where(StoredFile.id == file_id, StoredFile.user_id == user_id)
    if lock:
        query = query.with_for_update()
    file = db.scalar(query)
    if file is None:
        raise HTTPException(404, "File not found")
    return file


@router.post("", status_code=201)
async def upload(request: Request, user: CurrentUser, file: UploadFile = File(...),
                 db: Session = Depends(get_db)) -> dict:
    require_frontend_origin(request)
    name = PurePath((file.filename or "").replace("\\", "/")).name
    if not name or name in (".", "..") or len(name.encode()) > 255:
        raise HTTPException(400, "Choose a file with a valid name")
    content = await file.read(MAX_FILE_SIZE + 1)
    await file.close()
    if not content or len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "Choose a file up to 5 MiB")
    mime = file.content_type or "application/octet-stream"
    if "\r" in mime or "\n" in mime or len(mime) > 255:
        raise HTTPException(400, "Invalid file type")
    storage_token = await storage_access_token()
    owner = db.scalar(select(User).where(User.id == user.id).with_for_update()
                      .execution_options(populate_existing=True))
    if not owner.storage_folder_id:
        owner.storage_folder_id = await create_user_folder(storage_token, root_folder_id(), str(user.id))
        db.commit()
    try:
        storage_id = await upload_bytes(storage_token, name, mime, content,
                                        parent_id=owner.storage_folder_id)
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            raise HTTPException(502, "Central Drive rejected the upload") from None
        raise
    stored = StoredFile(user_id=user.id, filename=name, mime_type=mime,
                        size_bytes=len(content), content=None, storage_drive_file_id=storage_id)
    db.add(stored)
    db.commit()
    db.refresh(stored)
    return file_json(stored)


@router.get("")
def list_files(user: CurrentUser, db: Annotated[Session, Depends(get_db)],
               page: Annotated[int, Query(ge=1)] = 1,
               page_size: Annotated[int, Query(ge=1, le=50)] = 10) -> dict:
    owner = StoredFile.user_id == user.id
    total = db.scalar(select(func.count()).select_from(StoredFile).where(owner)) or 0
    files = db.scalars(select(StoredFile).where(owner)
                       .order_by(StoredFile.created_at.desc(), StoredFile.id.desc())
                       .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [file_json(file) for file in files], "total": total,
            "page": page, "page_size": page_size}


async def stored_bytes(file: StoredFile) -> bytes:
    if file.storage_drive_file_id:
        token = await storage_access_token()
        return await read_storage_file(token, file.storage_drive_file_id)
    if file.content is not None:  # Older rows remain readable until the PoC database is cleaned.
        return file.content
    raise HTTPException(502, "File content is unavailable")


@router.get("/{file_id}")
async def download(file_id: uuid.UUID, user: CurrentUser,
                   db: Annotated[Session, Depends(get_db)]) -> Response:
    file = owned_file(db, user.id, file_id)
    content = await stored_bytes(file)
    return Response(content, media_type=file.mime_type, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.filename)}",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/{file_id}/preview")
async def preview(file_id: uuid.UUID, user: CurrentUser,
                  db: Annotated[Session, Depends(get_db)]) -> Response:
    file = owned_file(db, user.id, file_id)
    content = await stored_bytes(file)
    return await preview_response(file.filename, content)


@router.post("/{file_id}/drive")
async def send_to_drive(file_id: uuid.UUID, request: Request,
                        user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    require_frontend_origin(request)
    owned_file(db, user.id, file_id)  # Reject another user's ID before checking Google.
    token = await access_token(user, db)
    file = owned_file(db, user.id, file_id, lock=True)
    if file.drive_file_id:
        return {"drive_file_id": file.drive_file_id, "uploaded": False}
    content = await stored_bytes(file)
    file.drive_file_id = await upload_bytes(token, file.filename, file.mime_type, content)
    db.commit()
    return {"drive_file_id": file.drive_file_id, "uploaded": True}


@router.post("/{file_id}/gmail-draft")
async def gmail_draft(file_id: uuid.UUID, payload: DraftRequest, request: Request,
                      user: CurrentUser, db: Session = Depends(get_db)) -> dict:
    require_frontend_origin(request)
    file = owned_file(db, user.id, file_id)
    token = await access_token(user, db, GMAIL_SCOPE)
    content = await stored_bytes(file)
    draft_id = await create_gmail_draft(token, str(payload.email), file.filename,
                                        file.mime_type, content)
    return {"draft_id": draft_id, "recipient": str(payload.email)}
