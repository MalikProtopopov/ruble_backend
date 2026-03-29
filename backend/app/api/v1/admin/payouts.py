"""Admin payout management endpoints."""

import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_admin
from app.repositories import foundation_repo, payout_repo
from app.schemas.payout import PayoutCreateRequest, PayoutResponse

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "",
    summary="List payouts",
    description="Список выплат фондам с фильтрацией по фонду и периоду",
)
async def list_payouts(
    foundation_id: UUID | None = Query(default=None),
    period_from: dt.date | None = Query(default=None),
    period_to: dt.date | None = Query(default=None),
    pagination: PaginationParams = Depends(get_pagination),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await payout_repo.list_payouts(
        session, pagination, foundation_id=foundation_id, period_from=period_from, period_to=period_to,
    )
    data = []
    for item in result["items"]:
        d = PayoutResponse.model_validate(item["payout"]).model_dump(mode="json")
        d["foundation_name"] = item["foundation_name"]
        data.append(d)
    return paginated_response(data, result["next_cursor"], result["has_more"])


@router.post(
    "",
    status_code=201,
    response_model=PayoutResponse,
    summary="Create payout",
    description="Регистрация выплаты фонду",
)
async def create_payout(
    body: PayoutCreateRequest,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    foundation = await foundation_repo.get_by_id(session, body.foundation_id)
    if foundation is None:
        raise NotFoundError(message="Фонд не найден")

    admin_id = UUID(admin["sub"])
    payout = await payout_repo.create(
        session,
        foundation_id=body.foundation_id,
        amount_kopecks=body.amount_kopecks,
        period_from=body.period_from,
        period_to=body.period_to,
        transfer_reference=body.transfer_reference,
        note=body.note,
        created_by_admin_id=admin_id,
    )

    logger.info(
        "payout_created",
        payout_id=str(payout.id),
        foundation_id=str(body.foundation_id),
        amount=body.amount_kopecks,
        admin_id=admin["sub"],
    )
    return PayoutResponse.model_validate(payout).model_dump(mode="json")


@router.get(
    "/balance",
    summary="Payout balances",
    description="Баланс выплат по фондам за период",
)
async def payout_balance(
    period_from: dt.date | None = Query(default=None),
    period_to: dt.date | None = Query(default=None),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    balances = await payout_repo.get_balance_by_foundation(session, period_from=period_from, period_to=period_to)
    return {"balances": balances}
