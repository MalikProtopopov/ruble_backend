"""Admin donation endpoints (refunds)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_admin
from app.schemas.base import ErrorResponse
from app.services import refund as refund_service

router = APIRouter()

_error_responses = {422: {"model": ErrorResponse, "description": "Ошибка валидации"}}


@router.post(
    "/{donation_id}/refund",
    summary="Refund a donation",
    description="Полный возврат успешного пожертвования через ЮKassa",
    responses=_error_responses,
)
async def refund_donation(
    donation_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _admin: dict = Depends(require_admin),
):
    return await refund_service.refund_donation(session, donation_id)
