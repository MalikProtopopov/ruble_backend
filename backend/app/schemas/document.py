"""Pydantic schemas for the documents module."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Admin schemas ---


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=2, max_length=255)
    excerpt: str | None = Field(default=None, max_length=500)
    content: str | None = None
    status: str = Field(default="draft")
    document_version: str | None = Field(default=None, max_length=50)
    document_date: date | None = None
    sort_order: int = 0


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=255)
    excerpt: str | None = Field(default=None, max_length=500)
    content: str | None = None
    status: str | None = None
    document_version: str | None = Field(default=None, max_length=50)
    document_date: date | None = None
    sort_order: int | None = None
    version: int = Field(..., description="Текущая версия для optimistic locking")


class DocumentAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    excerpt: str | None
    content: str | None
    status: str
    document_version: str | None
    document_date: date | None
    published_at: datetime | None
    file_url: str | None
    sort_order: int
    version: int
    created_at: datetime
    updated_at: datetime


# --- Public schemas ---


class DocumentPublicListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str
    excerpt: str | None
    document_version: str | None
    document_date: date | None
    published_at: datetime | None
    file_url: str | None


class DocumentPublicDetail(DocumentPublicListItem):
    content: str | None
