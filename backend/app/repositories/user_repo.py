"""User repository."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import desc, or_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.models import Donation, RefreshToken, Subscription, User
from app.models.base import PausedReason, SubscriptionStatus, UserRole
from app.repositories.base import cursor_paginate


async def get_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_admin(
    session: AsyncSession, pagination: PaginationParams, *, role: str | None = None, search: str | None = None,
) -> dict:
    query = select(User).where(User.is_deleted == False)
    if role:
        query = query.where(User.role == role)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(User.email.ilike(pattern), User.name.ilike(pattern), User.phone.ilike(pattern)))
    return await cursor_paginate(session, query, User, pagination)


async def get_subscriptions(session: AsyncSession, user_id: UUID) -> list[Subscription]:
    result = await session.execute(
        select(Subscription).where(Subscription.user_id == user_id, Subscription.is_deleted == False)
        .order_by(desc(Subscription.created_at))
    )
    return list(result.scalars().all())


async def get_recent_donations(session: AsyncSession, user_id: UUID, limit: int = 20) -> list[Donation]:
    result = await session.execute(
        select(Donation).where(Donation.user_id == user_id, Donation.is_deleted == False)
        .order_by(desc(Donation.created_at)).limit(limit)
    )
    return list(result.scalars().all())


async def set_role(session: AsyncSession, user: User, role: UserRole) -> User:
    user.role = role
    await session.flush()
    return user


async def set_active(session: AsyncSession, user: User, is_active: bool) -> User:
    user.is_active = is_active
    await session.flush()
    return user


async def revoke_all_tokens(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        sa_update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked == False)
        .values(is_revoked=True)
    )


async def pause_active_subscriptions(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        sa_update(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == SubscriptionStatus.active)
        .values(
            status=SubscriptionStatus.paused,
            paused_reason=PausedReason.user_request,
            paused_at=datetime.now(timezone.utc),
        )
    )
