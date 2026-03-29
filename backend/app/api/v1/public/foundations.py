"""Public foundation endpoints (no auth required)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import NotFoundError
from app.models import Foundation
from app.models.base import FoundationStatus
from app.schemas.foundation import FoundationPublicResponse

router = APIRouter(tags=["foundations"])


@router.get(
    "",
    summary="List active foundations",
    description="Список активных фондов для выбора при создании подписки",
)
async def list_foundations(
    search: str | None = Query(default=None, description="Поиск по названию"),
    session: AsyncSession = Depends(get_db_session),
):
    query = select(Foundation).where(Foundation.status == FoundationStatus.active).order_by(Foundation.name)
    if search:
        query = query.where(Foundation.name.ilike(f"%{search}%"))
    result = await session.execute(query)
    items = result.scalars().all()
    return [FoundationPublicResponse.model_validate(f).model_dump(mode="json") for f in items]


@router.get("/{foundation_id}", response_model=FoundationPublicResponse, summary="Get foundation public info", description="Публичная информация о фонде")
async def get_foundation(
    foundation_id: UUID,
    session: AsyncSession = Depends(get_db_session),
):
    result = await session.execute(select(Foundation).where(Foundation.id == foundation_id))
    foundation = result.scalar_one_or_none()
    if foundation is None:
        raise NotFoundError("Фонд не найден")
    return foundation
