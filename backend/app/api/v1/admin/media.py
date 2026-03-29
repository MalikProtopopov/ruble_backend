"""Admin media upload and library endpoints."""

import asyncio
import uuid
from uuid import UUID

import boto3
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select, update

from app.core.config import build_media_url, settings
from app.core.database import get_db_session
from app.core.exceptions import BusinessLogicError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_admin
from app.domain.media import FileTooLarge, InvalidFileFormat, validate_media
from app.models.base import MediaAssetType, uuid7
from app.repositories import media_repo
from app.schemas.media import MediaAssetDetailResponse, MediaAssetListItem, MediaUploadResponse

router = APIRouter()
logger = get_logger(__name__)

s3_client = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
)


def _list_item(row) -> dict:
    return MediaAssetListItem(
        id=row.id,
        key=row.s3_key,
        url=build_media_url(row.s3_key),
        type=row.type.value,
        filename=row.original_filename,
        size_bytes=row.size_bytes,
        content_type=row.content_type,
        created_at=row.created_at,
    ).model_dump(mode="json")


@router.get(
    "",
    summary="List media assets",
    description="Список загруженных файлов с курсорной пагинацией",
)
async def list_media(
    type: str | None = Query(default=None, description="video, document или audio"),
    search: str | None = Query(default=None, description="Поиск по имени файла или s3_key"),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    asset_type: MediaAssetType | None = None
    if type is not None:
        if type not in ("video", "document", "audio"):
            raise BusinessLogicError(
                code="INVALID_MEDIA_TYPE",
                message="Параметр type должен быть 'video', 'document' или 'audio'",
            )
        asset_type = MediaAssetType(type)
    result = await media_repo.list_admin(session, pagination, asset_type=asset_type, search=search)
    data = [_list_item(r) for r in result["items"]]
    return paginated_response(data, result["next_cursor"], result["has_more"])


@router.get(
    "/{media_id}/download",
    summary="Download media (redirect)",
    description="Редирект на публичный URL файла",
)
async def download_media(
    media_id: UUID,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    row = await media_repo.get_by_id(session, media_id)
    if row is None:
        raise NotFoundError(message="Файл не найден")
    return RedirectResponse(url=build_media_url(row.s3_key), status_code=302)


@router.get(
    "/{media_id}",
    summary="Get media asset detail",
    description="Метаданные файла и ссылки для просмотра/скачивания",
)
async def get_media(
    media_id: UUID,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    row = await media_repo.get_by_id(session, media_id)
    if row is None:
        raise NotFoundError(message="Файл не найден")
    media_url = build_media_url(row.s3_key)
    return MediaAssetDetailResponse(
        id=row.id,
        key=row.s3_key,
        url=media_url,
        type=row.type.value,
        filename=row.original_filename,
        size_bytes=row.size_bytes,
        content_type=row.content_type,
        created_at=row.created_at,
        download_url=media_url,
        uploaded_by_admin_id=row.uploaded_by_admin_id,
    ).model_dump(mode="json")


@router.post(
    "/upload",
    response_model=MediaUploadResponse,
    summary="Upload media file",
    description="Загрузка видео, документа или аудио в S3-хранилище",
)
async def upload_media(
    file: UploadFile = File(...),
    type: str = Form(..., description="video, document или audio"),
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    if type not in ("video", "document", "audio"):
        raise BusinessLogicError(
            code="INVALID_MEDIA_TYPE",
            message="Тип должен быть 'video', 'document' или 'audio'",
        )

    content = await file.read()
    size_bytes = len(content)
    content_type = file.content_type or "application/octet-stream"

    _too_large_msg = {
        "video": "Видео не должно превышать 500 МБ",
        "document": "Документ не должен превышать 10 МБ",
        "audio": "Аудио не должно превышать 50 МБ",
    }
    _format_label = {"video": "видео", "document": "документа", "audio": "аудио"}

    try:
        validate_media(type, content_type, size_bytes)
    except FileTooLarge:
        raise BusinessLogicError(code="FILE_TOO_LARGE", message=_too_large_msg[type])
    except InvalidFileFormat:
        label = _format_label[type]
        raise BusinessLogicError(
            code="INVALID_FILE_FORMAT",
            message=f"Недопустимый формат {label}: {content_type}",
        )

    prefix = {"video": "videos", "document": "documents", "audio": "audio"}[type]

    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[1].lower()

    key = f"{prefix}/{uuid.uuid4().hex}{ext}"

    await asyncio.to_thread(
        s3_client.put_object,
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=content_type,
    )

    url = build_media_url(key)
    media_id = uuid7()
    admin_uuid = UUID(admin["sub"]) if admin.get("sub") else None

    await media_repo.create(
        session,
        media_id=media_id,
        s3_key=key,
        public_url=url,
        asset_type=MediaAssetType(type),
        original_filename=file.filename or "",
        size_bytes=size_bytes,
        content_type=content_type,
        uploaded_by_admin_id=admin_uuid,
    )

    logger.info(
        "media_uploaded",
        media_id=str(media_id),
        key=key,
        size=size_bytes,
        content_type=content_type,
        admin_id=admin.get("sub"),
    )

    return MediaUploadResponse(
        id=media_id,
        key=key,
        url=url,
        filename=file.filename or "",
        size_bytes=size_bytes,
        content_type=content_type,
    ).model_dump()


@router.post(
    "/reindex-urls",
    summary="Reindex all media URLs",
    description="Пересчитывает public_url во всех media_assets, campaigns и foundations на основе текущего S3_PUBLIC_URL",
)
async def reindex_urls(
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    from app.models.campaign import Campaign
    from app.models.foundation import Foundation

    # 1. Update media_assets.public_url from s3_key
    assets = (await session.execute(select(MediaAsset))).scalars().all()
    asset_count = 0
    for asset in assets:
        new_url = build_media_url(asset.s3_key)
        if asset.public_url != new_url:
            asset.public_url = new_url
            asset_count += 1

    # 2. Build a mapping: old_url_suffix -> new_url for campaigns/foundations
    # Match by extracting the s3_key part from stored URLs
    url_map: dict[str, str] = {}
    for asset in assets:
        url_map[asset.s3_key] = build_media_url(asset.s3_key)

    # 3. Update campaigns.video_url and thumbnail_url
    campaigns = (await session.execute(select(Campaign))).scalars().all()
    campaign_count = 0
    for c in campaigns:
        updated = False
        for field in ("video_url", "thumbnail_url"):
            old_val = getattr(c, field)
            if old_val:
                for s3_key, new_url in url_map.items():
                    if old_val.endswith(s3_key):
                        setattr(c, field, new_url)
                        updated = True
                        break
        if updated:
            campaign_count += 1

    # 4. Update foundations.logo_url
    foundations = (await session.execute(select(Foundation))).scalars().all()
    foundation_count = 0
    for f in foundations:
        if f.logo_url:
            for s3_key, new_url in url_map.items():
                if f.logo_url.endswith(s3_key):
                    f.logo_url = new_url
                    foundation_count += 1
                    break

    # 5. Update campaign_documents.file_url
    from app.models.campaign import CampaignDocument
    docs = (await session.execute(select(CampaignDocument))).scalars().all()
    doc_count = 0
    for d in docs:
        if d.file_url:
            for s3_key, new_url in url_map.items():
                if d.file_url.endswith(s3_key):
                    d.file_url = new_url
                    doc_count += 1
                    break

    # 6. Update thanks_contents.media_url
    from app.models.campaign import ThanksContent
    thanks_list = (await session.execute(select(ThanksContent))).scalars().all()
    thanks_count = 0
    for t in thanks_list:
        if t.media_url:
            for s3_key, new_url in url_map.items():
                if t.media_url.endswith(s3_key):
                    t.media_url = new_url
                    thanks_count += 1
                    break

    await session.flush()

    logger.info(
        "media_urls_reindexed",
        assets=asset_count,
        campaigns=campaign_count,
        foundations=foundation_count,
    )
    return {
        "updated_assets": asset_count,
        "updated_campaigns": campaign_count,
        "updated_foundations": foundation_count,
        "updated_documents": doc_count,
        "updated_thanks": thanks_count,
    }
