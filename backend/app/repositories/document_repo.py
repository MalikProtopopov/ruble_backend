"""Data access layer for documents."""

from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.models.base import DocumentStatus, uuid7
from app.models.document import Document
from app.repositories.base import cursor_paginate


async def get_by_id(session: AsyncSession, doc_id: UUID) -> Document | None:
    result = await session.execute(
        select(Document).where(Document.id == doc_id, Document.is_deleted == False)  # noqa: E712
    )
    return result.scalar_one_or_none()


async def get_by_slug(session: AsyncSession, slug: str) -> Document | None:
    result = await session.execute(
        select(Document).where(
            Document.slug == slug,
            Document.is_deleted == False,  # noqa: E712
            Document.status == DocumentStatus.published,
        )
    )
    return result.scalar_one_or_none()


async def slug_exists(session: AsyncSession, slug: str, *, exclude_id: UUID | None = None) -> bool:
    query = select(Document.id).where(
        Document.slug == slug,
        Document.is_deleted == False,  # noqa: E712
    )
    if exclude_id:
        query = query.where(Document.id != exclude_id)
    result = await session.execute(query)
    return result.scalar_one_or_none() is not None


async def list_admin(
    session: AsyncSession,
    pagination: PaginationParams,
    *,
    status: str | None = None,
    search: str | None = None,
) -> dict:
    query = select(Document).where(Document.is_deleted == False)  # noqa: E712
    if status:
        query = query.where(Document.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.where(Document.title.ilike(pattern))
    return await cursor_paginate(session, query, Document, pagination)


async def list_published(
    session: AsyncSession,
    pagination: PaginationParams,
    *,
    search: str | None = None,
) -> dict:
    query = select(Document).where(
        Document.is_deleted == False,  # noqa: E712
        Document.status == DocumentStatus.published,
    )
    if search:
        pattern = f"%{search}%"
        query = query.where(Document.title.ilike(pattern))
    return await cursor_paginate(session, query, Document, pagination)


async def create(session: AsyncSession, **kwargs) -> Document:
    doc = Document(id=uuid7(), **kwargs)
    session.add(doc)
    await session.flush()
    await session.refresh(doc)
    return doc


async def update(session: AsyncSession, doc: Document, data: dict) -> Document:
    for field, value in data.items():
        setattr(doc, field, value)
    await session.flush()
    await session.refresh(doc)
    return doc
