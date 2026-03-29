"""Transaction endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_donor
from app.schemas.transaction import TransactionDetailResponse
from app.services import transaction as transaction_service

router = APIRouter(tags=["transactions"])


@router.get("", summary="List transactions", description="Список транзакций пользователя с фильтрацией")
async def list_transactions(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
    pagination: PaginationParams = Depends(get_pagination),
    tx_status: str | None = Query(default=None, alias="status"),
    campaign_id: UUID | None = Query(default=None),
    subscription_id: UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
):
    user_id = UUID(user["sub"])
    result = await transaction_service.list_transactions(
        session,
        user_id=user_id,
        limit=pagination.limit,
        cursor=pagination.cursor,
        status=tx_status,
        campaign_id=campaign_id,
        subscription_id=subscription_id,
        date_from=date_from,
        date_to=date_to,
    )
    return paginated_response(result["data"], result["next_cursor"], result["has_more"])


@router.get("/{transaction_id}", response_model=TransactionDetailResponse, summary="Get transaction detail", description="Детальная информация о транзакции")
async def get_transaction_detail(
    transaction_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await transaction_service.get_transaction_detail(session, user_id, transaction_id)
