
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FileMetadataResponse(BaseModel):
    """
    Public metadata for an uploaded file.

    Excludes the file's binary content
    and internal ownership information.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    filename: str

    mime_type: str

    size_bytes: int = Field(ge=0)

    created_at: datetime


class FileUploadResponse(FileMetadataResponse):
    """
    Response returned after a successful upload.
    """

    message: str = "File uploaded successfully"
