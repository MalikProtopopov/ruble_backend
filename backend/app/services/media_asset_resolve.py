"""Resolve MediaAsset rows to public URLs for PATCH bodies."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import build_media_url
from app.core.exceptions import BusinessLogicError, NotFoundError
from app.models.base import MediaAssetType
from app.repositories import media_repo

VIDEO_ONLY = frozenset({MediaAssetType.video})
THUMBNAIL_OR_LOGO = frozenset({MediaAssetType.video, MediaAssetType.document})


async def resolve_public_url(
    session: AsyncSession,
    asset_id: UUID,
    *,
    allowed_types: frozenset[MediaAssetType],
) -> str:
    row = await media_repo.get_by_id(session, asset_id)
    if row is None:
        raise NotFoundError(message="Медиафайл не найден")
    if row.type not in allowed_types:
        allowed = ", ".join(sorted(t.value for t in allowed_types))
        raise BusinessLogicError(
            code="INVALID_MEDIA_ASSET_TYPE",
            message=f"Для этого поля допустимы типы медиа: {allowed}",
        )
    return build_media_url(row.s3_key)
