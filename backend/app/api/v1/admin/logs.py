"""Admin log viewing endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_admin
from app.models.base import AllocationChangeReason, NotificationStatus
from app.repositories import log_repo
from app.schemas.notification import NotificationLogResponse

router = APIRouter()


@router.get(
    "/allocation-logs",
    summary="List allocation logs",
    description="Логи реаллокации подписок",
)
async def list_allocation_logs(
    subscription_id: UUID | None = Query(default=None),
    reason: AllocationChangeReason | None = Query(default=None),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await log_repo.list_allocation_logs(
        session, pagination, subscription_id=subscription_id, reason=reason,
    )
    # Items are already pre-serialized dicts from the repo (due to complex join)
    return paginated_response(result["items"], result["next_cursor"], result["has_more"])


@router.get(
    "/notification-logs",
    summary="List notification logs",
    description="Логи отправки уведомлений",
)
async def list_notification_logs(
    user_id: UUID | None = Query(default=None),
    notification_type: str | None = Query(default=None),
    status: NotificationStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await log_repo.list_notification_logs(
        session, pagination, user_id=user_id, notification_type=notification_type, status=status,
    )
    data = [NotificationLogResponse.model_validate(n).model_dump(mode="json") for n in result["items"]]
    return paginated_response(data, result["next_cursor"], result["has_more"])
