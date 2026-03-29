"""Impact & achievements service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models import Achievement, User, UserAchievement
from app.models.base import AchievementConditionType

logger = get_logger(__name__)


async def get_impact(session: AsyncSession, user_id: UUID) -> dict:
    result = await session.execute(select(User).where(User.id == user_id, User.is_deleted == False))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("Пользователь не найден")
    return {
        "total_donated_kopecks": user.total_donated_kopecks,
        "streak_days": user.current_streak_days,
        "donations_count": user.total_donations_count,
    }


async def get_achievements(session: AsyncSession, user_id: UUID) -> list[dict]:
    result = await session.execute(
        select(Achievement, UserAchievement.earned_at)
        .outerjoin(
            UserAchievement,
            (UserAchievement.achievement_id == Achievement.id) & (UserAchievement.user_id == user_id),
        )
        .where(Achievement.is_active == True)
        .order_by(Achievement.code)
    )
    rows = result.all()
    return [
        {
            "id": ach.id,
            "code": ach.code,
            "title": ach.title,
            "description": ach.description,
            "icon_url": ach.icon_url,
            "earned_at": earned_at,
        }
        for ach, earned_at in rows
    ]


async def check_and_award_achievements(session: AsyncSession, user_id: UUID) -> list[Achievement]:
    """Check all active achievements against user stats and award new ones.

    Called after a successful payment. Returns list of newly awarded achievements.
    """
    user_result = await session.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        return []

    # Refresh to pick up any raw SQL updates (e.g., from update_user_impact)
    await session.refresh(user)

    # Already-earned achievement IDs
    earned_result = await session.execute(
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user_id)
    )
    earned_ids = {row[0] for row in earned_result.all()}

    # All active achievements
    ach_result = await session.execute(select(Achievement).where(Achievement.is_active == True))
    all_achievements = list(ach_result.scalars().all())

    newly_awarded: list[Achievement] = []

    for ach in all_achievements:
        if ach.id in earned_ids:
            continue

        qualified = False
        if ach.condition_type == AchievementConditionType.streak_days:
            qualified = user.current_streak_days >= ach.condition_value
        elif ach.condition_type == AchievementConditionType.total_amount_kopecks:
            qualified = user.total_donated_kopecks >= ach.condition_value
        elif ach.condition_type == AchievementConditionType.donations_count:
            qualified = user.total_donations_count >= ach.condition_value

        if qualified:
            ua = UserAchievement(id=uuid7(), user_id=user_id, achievement_id=ach.id)
            session.add(ua)
            newly_awarded.append(ach)
            logger.info("achievement_awarded", user_id=str(user_id), achievement_code=ach.code)

    if newly_awarded:
        await session.flush()

    return newly_awarded
