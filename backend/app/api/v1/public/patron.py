"""Patron payment link endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_patron
from app.schemas.patron import CreatePaymentLinkRequest, PaymentLinkResponse
from app.services import patron as patron_service

router = APIRouter(tags=["patron"])


@router.post("", response_model=PaymentLinkResponse, status_code=status.HTTP_201_CREATED, summary="Create payment link", description="Создание платёжной ссылки мецената")
async def create_payment_link(
    body: CreatePaymentLinkRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_patron),
):
    user_id = UUID(user["sub"])
    return await patron_service.create_payment_link(
        session, user_id, body.campaign_id, body.amount_kopecks,
    )


@router.get("", summary="List payment links", description="Список платёжных ссылок мецената")
async def list_payment_links(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_patron),
    pagination: PaginationParams = Depends(get_pagination),
    link_status: str | None = Query(default=None, alias="status"),
):
    user_id = UUID(user["sub"])
    result = await patron_service.list_payment_links(
        session, user_id, limit=pagination.limit, cursor=pagination.cursor, status=link_status,
    )
    return paginated_response(result["data"], result["next_cursor"], result["has_more"])


@router.get("/{link_id}", response_model=PaymentLinkResponse, summary="Get payment link detail", description="Детальная информация о платёжной ссылке")
async def get_payment_link(
    link_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_patron),
):
    user_id = UUID(user["sub"])
    return await patron_service.get_payment_link(session, link_id, user_id)
