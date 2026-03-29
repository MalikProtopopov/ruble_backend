"""Admin statistics endpoints."""

import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import NotFoundError
from app.core.security import require_admin
from app.repositories import stats_repo

router = APIRouter()


@router.get(
    "/overview",
    summary="Overview statistics",
    description="Общая статистика платформы за период",
)
async def overview_stats(
    period_from: dt.date | None = Query(default=None),
    period_to: dt.date | None = Query(default=None),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    return await stats_repo.get_overview_stats(session, period_from=period_from, period_to=period_to)


@router.get(
    "/campaigns/{campaign_id}",
    summary="Campaign statistics",
    description="Статистика конкретной кампании",
)
async def campaign_stats(
    campaign_id: UUID,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    result = await stats_repo.get_campaign_stats(session, campaign_id)
    if result is None:
        raise NotFoundError(message="Кампания не найдена")
    return result
