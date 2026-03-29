"""Media asset repository (admin library)."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.models import MediaAsset
from app.models.base import MediaAssetType
from app.repositories.base import cursor_paginate


async def create(
    session: AsyncSession,
    *,
    media_id: UUID,
    s3_key: str,
    public_url: str,
    asset_type: MediaAssetType,
    original_filename: str,
    size_bytes: int,
    content_type: str,
    uploaded_by_admin_id: UUID | None,
) -> MediaAsset:
    row = MediaAsset(
        id=media_id,
        s3_key=s3_key,
        public_url=public_url,
        type=asset_type,
        original_filename=original_filename,
        size_bytes=size_bytes,
        content_type=content_type,
        uploaded_by_admin_id=uploaded_by_admin_id,
    )
    session.add(row)
    await session.flush()
    return row


async def get_by_id(session: AsyncSession, media_id: UUID) -> MediaAsset | None:
    result = await session.execute(select(MediaAsset).where(MediaAsset.id == media_id))
    return result.scalar_one_or_none()


async def list_admin(
    session: AsyncSession,
    pagination: PaginationParams,
    *,
    asset_type: MediaAssetType | None = None,
    search: str | None = None,
) -> dict:
    query = select(MediaAsset)
    if asset_type is not None:
        query = query.where(MediaAsset.type == asset_type)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(MediaAsset.original_filename.ilike(pattern), MediaAsset.s3_key.ilike(pattern)),
        )
    return await cursor_paginate(session, query, MediaAsset, pagination)
