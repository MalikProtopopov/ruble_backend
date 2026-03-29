"""Thanks content endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_donor
from app.services import thanks as thanks_service

router = APIRouter(tags=["thanks"])


@router.get("/unseen", summary="Get unseen thanks", description="Непросмотренные благодарности от фондов")
async def get_unseen_thanks(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await thanks_service.get_unseen_thanks(session, user_id)


@router.get("/{thanks_id}", summary="Get thanks detail", description="Детальная информация о благодарности")
async def get_thanks_detail(
    thanks_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await thanks_service.get_thanks_detail(session, thanks_id, user_id)
