"""User profile service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models import User

logger = get_logger(__name__)


async def get_profile(session: AsyncSession, user_id: UUID) -> User:
    result = await session.execute(select(User).where(User.id == user_id, User.is_deleted == False))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("Пользователь не найден")
    return user


async def update_profile(session: AsyncSession, user_id: UUID, data: dict) -> User:
    user = await get_profile(session, user_id)
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    await session.flush()
    return user


async def update_notifications(session: AsyncSession, user_id: UUID, data: dict) -> dict:
    user = await get_profile(session, user_id)
    prefs = dict(user.notification_preferences or {})
    for key, value in data.items():
        if value is not None:
            prefs[key] = value
    user.notification_preferences = prefs
    await session.flush()
    return prefs


async def anonymize_user(session: AsyncSession, user_id: UUID) -> None:
    """Soft-delete + anonymize PD (ФЗ-152). Subscriptions cancelled."""
    from sqlalchemy import update as sa_update
    from app.models import Subscription
    from app.models.base import SubscriptionStatus
    from datetime import datetime, timezone

    user = await get_profile(session, user_id)
    user.email = f"deleted_{user.id}@anonymized.local"
    user.phone = None
    user.name = None
    user.avatar_url = None
    user.push_token = None
    user.is_deleted = True
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)

    # Cancel all active subscriptions
    await session.execute(
        sa_update(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status.in_(["active", "paused", "pending_payment_method"]))
        .values(status=SubscriptionStatus.cancelled, cancelled_at=datetime.now(timezone.utc))
    )

    # Revoke all refresh tokens
    from app.models import RefreshToken
    await session.execute(
        sa_update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked == False)
        .values(is_revoked=True)
    )

    await session.flush()
    logger.info("user_anonymized", user_id=str(user_id))
