"""Impact & achievements endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_donor
from app.schemas.impact import AchievementResponse, ImpactResponse
from app.services import impact as impact_service

router = APIRouter(tags=["impact"])


@router.get("", response_model=ImpactResponse, summary="Get user impact summary", description="Сводка импакта пользователя")
async def get_impact(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await impact_service.get_impact(session, user_id)


@router.get("/achievements", response_model=list[AchievementResponse], summary="Get achievements", description="Список достижений пользователя")
async def get_achievements(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await impact_service.get_achievements(session, user_id)
