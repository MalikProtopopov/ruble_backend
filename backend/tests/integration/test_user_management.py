"""Integration tests for user profile, notifications, anonymization, impact, achievements."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import NotFoundError
from app.models import (
    Achievement,
    RefreshToken,
    Subscription,
    User,
    UserAchievement,
)
from app.models.base import (
    AchievementConditionType,
    SubscriptionStatus,
    UserRole,
)
from app.services.impact import check_and_award_achievements, get_achievements, get_impact
from app.services.user import anonymize_user, get_profile, update_notifications, update_profile
from tests.conftest import (
    create_refresh_token_record,
    create_subscription,
    create_user,
)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


async def test_get_profile(db: AsyncSession, user: User):
    """get_profile returns user data."""
    profile = await get_profile(db, user.id)

    assert str(profile.id) == str(user.id)
    assert profile.email == user.email


async def test_update_profile(db: AsyncSession, user: User):
    """update_profile persists name and phone changes."""
    updated = await update_profile(db, user.id, {"name": "New Name", "phone": "+79001234567"})

    assert updated.name == "New Name"
    assert updated.phone == "+79001234567"

    await db.refresh(user)
    assert user.name == "New Name"


async def test_update_notifications(db: AsyncSession, user: User):
    """update_notifications merges preferences."""
    prefs = await update_notifications(db, user.id, {"push_daily_streak": True})

    assert prefs["push_daily_streak"] is True
    # Other defaults should be preserved
    assert prefs["push_on_payment"] is True


# ---------------------------------------------------------------------------
# Anonymize
# ---------------------------------------------------------------------------


async def test_anonymize_user(db: AsyncSession):
    """anonymize_user nullifies PD, cancels subs, revokes tokens."""
    user = await create_user(db, name="John Doe")
    sub = await create_subscription(db, user, status=SubscriptionStatus.active)
    rt, _raw = await create_refresh_token_record(db, user_id=user.id)

    await anonymize_user(db, user.id)

    await db.refresh(user)
    assert user.is_deleted is True
    assert user.is_active is False
    assert user.name is None
    assert user.phone is None
    assert "anonymized" in user.email

    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.cancelled

    await db.refresh(rt)
    assert rt.is_revoked is True


# ---------------------------------------------------------------------------
# Impact
# ---------------------------------------------------------------------------


async def test_get_impact(db: AsyncSession, user: User):
    """get_impact returns cached user totals."""
    from app.services.payment import update_user_impact

    await update_user_impact(db, user.id, 7000)
    await db.refresh(user)

    impact = await get_impact(db, user.id)

    assert impact["total_donated_kopecks"] == 7000
    assert impact["donations_count"] == 1
    assert impact["streak_days"] == 0  # no streak call made


# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------


async def test_get_achievements(db: AsyncSession, user: User):
    """get_achievements returns all active achievements with earned_at for earned ones."""
    ach1 = Achievement(
        id=uuid7(),
        code="STREAK_7",
        title="7 Day Streak",
        condition_type=AchievementConditionType.streak_days,
        condition_value=7,
        is_active=True,
    )
    ach2 = Achievement(
        id=uuid7(),
        code="FIRST_100",
        title="First 100 rub",
        condition_type=AchievementConditionType.total_amount_kopecks,
        condition_value=10000,
        is_active=True,
    )
    db.add(ach1)
    await db.flush()
    db.add(ach2)
    await db.flush()

    # Earn one achievement
    ua = UserAchievement(id=uuid7(), user_id=user.id, achievement_id=ach2.id)
    db.add(ua)
    await db.flush()

    achievements = await get_achievements(db, user.id)

    codes = {a["code"]: a for a in achievements}
    assert "STREAK_7" in codes
    assert codes["STREAK_7"]["earned_at"] is None
    assert "FIRST_100" in codes
    assert codes["FIRST_100"]["earned_at"] is not None
