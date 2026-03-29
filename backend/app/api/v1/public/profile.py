"""User profile endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import require_donor
from app.schemas.user import (
    UpdateNotificationsRequest,
    UpdateProfileRequest,
    UserProfileResponse,
)
from app.services import user as user_service

router = APIRouter(tags=["profile"])


@router.get("", response_model=UserProfileResponse, summary="Get current user profile", description="Профиль текущего авторизованного пользователя")
async def get_profile(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await user_service.get_profile(session, user_id)


@router.patch("", response_model=UserProfileResponse, summary="Update profile", description="Обновление данных профиля")
async def update_profile(
    body: UpdateProfileRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await user_service.update_profile(session, user_id, body.model_dump(exclude_unset=True))


@router.patch("/notifications", summary="Update notification preferences", description="Настройка уведомлений пользователя")
async def update_notifications(
    body: UpdateNotificationsRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    return await user_service.update_notifications(session, user_id, body.model_dump(exclude_unset=True))


@router.delete("", status_code=204, summary="Delete account (anonymize)", description="Удаление аккаунта с анонимизацией данных")
async def delete_account(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    await user_service.anonymize_user(session, user_id)
    return Response(status_code=204)
