from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MediaUploadResponse(BaseModel):
    id: UUID
    key: str
    url: str
    filename: str
    size_bytes: int
    content_type: str


class MediaAssetListItem(BaseModel):
    id: UUID
    key: str
    url: str
    type: str
    filename: str
    size_bytes: int
    content_type: str
    created_at: datetime


class MediaAssetDetailResponse(MediaAssetListItem):
    """Detail includes explicit download_url (same as url when bucket is public)."""

    download_url: str
    uploaded_by_admin_id: UUID | None = None
