"""Public endpoints for published documents."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import NotFoundError
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.repositories import document_repo
from app.schemas.document import DocumentPublicDetail, DocumentPublicListItem

router = APIRouter()


@router.get(
    "",
    summary="List published documents",
    description="Список опубликованных документов (без полного содержимого)",
)
async def list_documents(
    search: str | None = Query(default=None, description="Поиск по названию"),
    pagination: PaginationParams = Depends(get_pagination),
    session: AsyncSession = Depends(get_db_session),
):
    result = await document_repo.list_published(session, pagination, search=search)
    data = [
        DocumentPublicListItem.model_validate(d).model_dump(mode="json")
        for d in result["items"]
    ]
    return paginated_response(data, result["next_cursor"], result["has_more"])


@router.get(
    "/{slug}",
    summary="Get document by slug",
    description="Получение опубликованного документа по slug",
)
async def get_document_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
):
    doc = await document_repo.get_by_slug(session, slug)
    if doc is None:
        raise NotFoundError(message="Документ не найден")
    return DocumentPublicDetail.model_validate(doc).model_dump(mode="json")
