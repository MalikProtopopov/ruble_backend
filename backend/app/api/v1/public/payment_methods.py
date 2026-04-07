"""Saved payment methods — user-facing CRUD."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_donor
from app.schemas.payment_method import PaymentMethodResponse
from app.services import payment_method as pm_service

router = APIRouter(tags=["payment-methods"])


@router.get(
    "",
    response_model=list[PaymentMethodResponse],
    summary="List saved payment methods",
    description="Сохранённые способы оплаты текущего пользователя (без полных данных карты).",
)
async def list_payment_methods(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    return await pm_service.list_for_user(session, UUID(user["sub"]))


@router.delete(
    "/{pm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved payment method",
)
async def delete_payment_method(
    pm_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    await pm_service.delete_for_user(session, pm_id, UUID(user["sub"]))
    return Response(status_code=204)


@router.post(
    "/{pm_id}/set-default",
    response_model=PaymentMethodResponse,
    summary="Set a payment method as default",
)
async def set_default(
    pm_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    return await pm_service.set_default_for_user(session, pm_id, UUID(user["sub"]))
