"""User profile endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import require_donor
from app.schemas.user import (
    NotificationPreferences,
    UpdateNotificationsRequest,
    UpdateProfileRequest,
    UserProfileResponse,
)
from app.services import user as user_service

router = APIRouter(tags=["profile"])


def _profile_response(user) -> UserProfileResponse:
    prefs_data = dict(user.notification_preferences or {})
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        name=user.name,
        avatar_url=user.avatar_url,
        role=user.role.value if hasattr(user.role, "value") else user.role,
        timezone=user.timezone,
        is_anonymous=user.is_anonymous,
        is_email_verified=user.is_email_verified,
        notification_preferences=NotificationPreferences(**prefs_data),
        current_streak_days=user.current_streak_days or 0,
        total_donated_kopecks=user.total_donated_kopecks or 0,
        total_donations_count=user.total_donations_count or 0,
        donation_cooldown_hours=settings.DONATION_COOLDOWN_HOURS,
        created_at=user.created_at,
    )


@router.get("", response_model=UserProfileResponse, summary="Get current user profile", description="Профиль текущего авторизованного пользователя")
async def get_profile(
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    user_obj = await user_service.get_profile(session, user_id)
    return _profile_response(user_obj)


@router.patch("", response_model=UserProfileResponse, summary="Update profile", description="Обновление данных профиля")
async def update_profile(
    body: UpdateProfileRequest,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    user_id = UUID(user["sub"])
    user_obj = await user_service.update_profile(session, user_id, body.model_dump(exclude_unset=True))
    return _profile_response(user_obj)


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
