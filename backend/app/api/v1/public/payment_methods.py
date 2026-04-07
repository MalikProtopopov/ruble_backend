"""Saved payment methods — user-facing CRUD."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_donor
from app.schemas.payment_method import (
    OrphanedAccountPreview,
    PaymentMethodResponse,
    RecoveryResult,
)
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


@router.get(
    "/orphans",
    response_model=list[OrphanedAccountPreview],
    summary="Find orphaned anonymous accounts that share any of the user's saved cards",
    description=(
        "Scan-вариант recovery-flow: проходит по ВСЕМ сохранённым картам текущего "
        "юзера и возвращает анонимные аккаунты, у которых есть карты с такими же "
        "fingerprint'ами. Используется мобилкой как **рекомендуемый** способ — "
        "не нужно знать конкретный `pm_id` свежесохранённой карты, не надо ждать "
        "вебхук YooKassa. Достаточно сделать запрос после любого успешного "
        "сохранения карты."
    ),
)
async def list_all_orphans_for_user(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    return await pm_service.find_all_orphaned_accounts_for_user(
        session, current_user_id=UUID(user["sub"])
    )


@router.post(
    "/recover",
    response_model=RecoveryResult,
    summary="Merge orphans matching any of the user's saved cards",
    description=(
        "Scan-вариант POST /recover — мерджит все аноним-аккаунты, у которых "
        "fingerprint совпадает хотя бы с одной картой текущего юзера. Идемпотентно: "
        "повторный вызов вернёт пустой `merged_user_ids` если орфанов больше нет."
    ),
)
async def recover_all_orphans_for_user(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    return await pm_service.recover_all_orphaned_accounts_for_user(
        session, current_user_id=UUID(user["sub"])
    )


@router.get(
    "/{pm_id}/orphans",
    response_model=list[OrphanedAccountPreview],
    summary="Find orphaned anonymous accounts holding the same card",
    description=(
        "После сохранения карты на новой инсталляции мобильного приложения "
        "проверяет, есть ли другие анонимные аккаунты с той же физической картой "
        "(совпадение по `card_fingerprint`). Возвращает список превью — что было "
        "потеряно — чтобы UI мог показать «У вас была активная подписка на "
        "прошлой установке, восстановить?»."
    ),
)
async def list_orphans(
    pm_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    return await pm_service.find_orphaned_accounts(
        session, pm_id=pm_id, current_user_id=UUID(user["sub"])
    )


@router.post(
    "/{pm_id}/recover",
    response_model=RecoveryResult,
    summary="Merge orphaned anonymous accounts into the current user",
    description=(
        "Подтверждает восстановление: переносит донаты, подписки и сохранённые "
        "карты со всех найденных по `card_fingerprint` анонимных аккаунтов на "
        "текущего пользователя. Источники soft-deleted, refresh-токены отозваны."
    ),
)
async def recover_orphans(
    pm_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    return await pm_service.recover_orphaned_accounts(
        session, pm_id=pm_id, current_user_id=UUID(user["sub"])
    )
