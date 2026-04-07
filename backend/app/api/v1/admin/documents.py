"""Admin CRUD for legal/corporate documents."""

import asyncio
import uuid
from datetime import datetime, timezone
from uuid import UUID

import boto3
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import build_media_url, settings
from app.core.database import get_db_session
from app.core.exceptions import BusinessLogicError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_admin
from app.models.base import DocumentStatus
from app.repositories import document_repo
from app.schemas.document import (
    DocumentAdminResponse,
    DocumentCreate,
    DocumentUpdate,
)

router = APIRouter()
logger = get_logger(__name__)

s3_client = boto3.client(
    "s3",
    endpoint_url=settings.S3_ENDPOINT_URL,
    aws_access_key_id=settings.S3_ACCESS_KEY,
    aws_secret_access_key=settings.S3_SECRET_KEY,
)

ALLOWED_FILE_TYPES = frozenset({
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
})
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _serialize(doc) -> dict:
    return DocumentAdminResponse.model_validate(doc).model_dump(mode="json")


@router.get(
    "",
    summary="List documents",
    description="Список документов с фильтрацией по статусу и поиском",
)
async def list_documents(
    status: str | None = Query(default=None, description="draft, published или archived"),
    search: str | None = Query(default=None, description="Поиск по названию"),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await document_repo.list_admin(session, pagination, status=status, search=search)
    data = [_serialize(d) for d in result["items"]]
    return paginated_response(data, result["next_cursor"], result["has_more"])


@router.post(
    "",
    status_code=201,
    summary="Create document",
    description="Создание нового документа",
)
async def create_document(
    body: DocumentCreate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    if body.status not in ("draft", "published", "archived"):
        raise BusinessLogicError(code="INVALID_STATUS", message="Статус должен быть draft, published или archived")

    if await document_repo.slug_exists(session, body.slug):
        raise ConflictError(message="Документ с таким slug уже существует", details={"code": "SLUG_ALREADY_EXISTS"})

    create_data = body.model_dump()
    status_val = create_data.pop("status")
    doc = await document_repo.create(session, status=DocumentStatus(status_val), **create_data)

    if status_val == "published":
        doc.publish()
        await session.flush()
        await session.refresh(doc)

    logger.info("document_created", document_id=str(doc.id), admin_id=admin["sub"])
    return _serialize(doc)


@router.get(
    "/{document_id}",
    summary="Get document",
    description="Получение документа по ID",
)
async def get_document(
    document_id: UUID,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await document_repo.get_by_id(session, document_id)
    if doc is None:
        raise NotFoundError(message="Документ не найден")
    return _serialize(doc)


@router.patch(
    "/{document_id}",
    summary="Update document",
    description="Обновление документа (optimistic locking через поле version)",
)
async def update_document(
    document_id: UUID,
    body: DocumentUpdate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await document_repo.get_by_id(session, document_id)
    if doc is None:
        raise NotFoundError(message="Документ не найден")

    if body.version != doc.version:
        raise ConflictError(
            message="Документ был изменён другим пользователем. Обновите страницу.",
            details={"code": "VERSION_CONFLICT", "current_version": doc.version},
        )

    update_data = body.model_dump(exclude_unset=True)
    update_data.pop("version", None)

    if "slug" in update_data and update_data["slug"] != doc.slug:
        if await document_repo.slug_exists(session, update_data["slug"], exclude_id=document_id):
            raise ConflictError(message="Документ с таким slug уже существует", details={"code": "SLUG_ALREADY_EXISTS"})

    if "status" in update_data:
        status_val = update_data["status"]
        if status_val not in ("draft", "published", "archived"):
            raise BusinessLogicError(code="INVALID_STATUS", message="Статус должен быть draft, published или archived")
        update_data["status"] = DocumentStatus(status_val)
        if status_val == "published" and doc.published_at is None:
            update_data["published_at"] = datetime.now(timezone.utc)

    update_data["version"] = doc.version + 1

    doc = await document_repo.update(session, doc, update_data)
    logger.info("document_updated", document_id=str(document_id), admin_id=admin["sub"])
    return _serialize(doc)


@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Delete document (soft)",
    description="Мягкое удаление документа",
)
async def delete_document(
    document_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await document_repo.get_by_id(session, document_id)
    if doc is None:
        raise NotFoundError(message="Документ не найден")

    doc.is_deleted = True
    doc.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    logger.info("document_deleted", document_id=str(document_id), admin_id=admin["sub"])


@router.post(
    "/{document_id}/publish",
    summary="Publish document",
    description="Публикация документа",
)
async def publish_document(
    document_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await document_repo.get_by_id(session, document_id)
    if doc is None:
        raise NotFoundError(message="Документ не найден")

    doc.publish()
    doc.version += 1
    await session.flush()
    await session.refresh(doc)

    logger.info("document_published", document_id=str(document_id), admin_id=admin["sub"])
    return _serialize(doc)


@router.post(
    "/{document_id}/unpublish",
    summary="Unpublish document",
    description="Перевод документа в черновик",
)
async def unpublish_document(
    document_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await document_repo.get_by_id(session, document_id)
    if doc is None:
        raise NotFoundError(message="Документ не найден")

    doc.unpublish()
    doc.version += 1
    await session.flush()
    await session.refresh(doc)

    logger.info("document_unpublished", document_id=str(document_id), admin_id=admin["sub"])
    return _serialize(doc)


@router.post(
    "/{document_id}/file",
    summary="Upload document file",
    description="Загрузка файла к документу (PDF, DOCX, XLSX и др., до 50 МБ)",
)
async def upload_file(
    document_id: UUID,
    file: UploadFile = File(...),
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await document_repo.get_by_id(session, document_id)
    if doc is None:
        raise NotFoundError(message="Документ не найден")

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"

    if content_type not in ALLOWED_FILE_TYPES:
        raise BusinessLogicError(
            code="INVALID_FILE_FORMAT",
            message="Допустимые форматы: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, CSV",
        )
    if len(content) > MAX_FILE_SIZE:
        raise BusinessLogicError(code="FILE_TOO_LARGE", message="Файл не должен превышать 50 МБ")

    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[1].lower()

    key = f"documents/{uuid.uuid4().hex}{ext}"

    await asyncio.to_thread(
        s3_client.put_object,
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=content_type,
    )

    doc.file_url = build_media_url(key)
    doc.version += 1
    await session.flush()
    await session.refresh(doc)

    logger.info("document_file_uploaded", document_id=str(document_id), key=key, admin_id=admin["sub"])
    return _serialize(doc)


@router.delete(
    "/{document_id}/file",
    summary="Delete document file",
    description="Удаление файла документа из хранилища",
)
async def delete_file(
    document_id: UUID,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    doc = await document_repo.get_by_id(session, document_id)
    if doc is None:
        raise NotFoundError(message="Документ не найден")

    if not doc.file_url:
        raise BusinessLogicError(code="NO_FILE", message="У документа нет прикреплённого файла")

    # Extract S3 key from URL and delete
    s3_key = doc.file_url.rsplit("/media/", 1)[-1] if "/media/" in doc.file_url else None
    if s3_key:
        try:
            await asyncio.to_thread(
                s3_client.delete_object,
                Bucket=settings.S3_BUCKET,
                Key=s3_key,
            )
        except Exception:
            logger.warning("document_file_delete_failed", document_id=str(document_id), key=s3_key)

    doc.file_url = None
    doc.version += 1
    await session.flush()
    await session.refresh(doc)

    logger.info("document_file_deleted", document_id=str(document_id), admin_id=admin["sub"])
    return _serialize(doc)
