"""Integration tests for campaign lifecycle, allocation, streaks, and impact."""

import datetime as dt
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.models import Campaign, Foundation, Subscription, User
from app.models.base import (
    AllocationChangeReason,
    AllocationStrategy,
    CampaignStatus,
    FoundationStatus,
    PausedReason,
    SubscriptionStatus,
)
from app.services.allocation import (
    find_campaign_for_subscription,
    reallocate_campaign_subscriptions,
    reallocate_subscription,
)
from app.services.payment import (
    check_campaign_auto_complete,
    increment_campaign_counters,
    process_successful_payment,
    update_user_impact,
    update_user_streak,
)
from tests.conftest import (
    create_campaign,
    create_foundation,
    create_subscription,
    create_user,
)


# ---------------------------------------------------------------------------
# Auto-complete on goal reached
# ---------------------------------------------------------------------------


async def test_auto_complete_on_goal_reached(db: AsyncSession, user: User, foundation: Foundation):
    """Campaign with goal_amount auto-completes when collected >= goal."""
    campaign = await create_campaign(
        db, foundation, goal_amount=10000, collected_amount=0
    )

    # Simulate a payment that pushes collected_amount past the goal
    await process_successful_payment(db, campaign.id, user.id, 10000)

    await db.refresh(campaign)
    assert campaign.status == CampaignStatus.completed
    assert campaign.collected_amount >= 10000


async def test_offline_payment_increments_collected(
    db: AsyncSession, foundation: Foundation
):
    """increment_campaign_counters atomically updates collected_amount."""
    campaign = await create_campaign(db, foundation, collected_amount=0)

    await increment_campaign_counters(db, campaign.id, 3000, user_id=None)
    await increment_campaign_counters(db, campaign.id, 2000, user_id=None)

    await db.refresh(campaign)
    assert campaign.collected_amount == 5000


# ---------------------------------------------------------------------------
# Allocation strategies
# ---------------------------------------------------------------------------


async def test_allocation_platform_pool(db: AsyncSession, user: User):
    """Platform pool selects highest urgency active campaign."""
    f = await create_foundation(db, status=FoundationStatus.active)
    low = await create_campaign(db, f, urgency_level=1, title="Low")
    high = await create_campaign(db, f, urgency_level=5, title="High")

    sub = await create_subscription(
        db,
        user,
        allocation_strategy=AllocationStrategy.platform_pool,
        status=SubscriptionStatus.active,
    )

    campaign_id = await find_campaign_for_subscription(db, sub)
    assert str(campaign_id) == str(high.id)


async def test_allocation_foundation_pool(db: AsyncSession, user: User):
    """Foundation pool selects from specific foundation, falls back to platform."""
    f1 = await create_foundation(db, name="F1", status=FoundationStatus.active)
    f2 = await create_foundation(db, name="F2", status=FoundationStatus.active)
    c1 = await create_campaign(db, f1, urgency_level=3, title="F1 Campaign")
    c2 = await create_campaign(db, f2, urgency_level=5, title="F2 Campaign")

    sub = await create_subscription(
        db,
        user,
        allocation_strategy=AllocationStrategy.foundation_pool,
        foundation_id=f1.id,
        status=SubscriptionStatus.active,
    )

    campaign_id = await find_campaign_for_subscription(db, sub)
    assert str(campaign_id) == str(c1.id)  # should pick from f1, not f2


async def test_allocation_specific_campaign(
    db: AsyncSession, user: User, foundation: Foundation
):
    """Specific campaign strategy uses the bound campaign, falls back if completed."""
    active_c = await create_campaign(db, foundation, title="Active", urgency_level=4)
    fallback_c = await create_campaign(db, foundation, title="Fallback", urgency_level=5)

    sub = await create_subscription(
        db,
        user,
        allocation_strategy=AllocationStrategy.specific_campaign,
        campaign_id=active_c.id,
        foundation_id=foundation.id,
        status=SubscriptionStatus.active,
    )

    # While active, it returns the bound campaign
    campaign_id = await find_campaign_for_subscription(db, sub)
    assert str(campaign_id) == str(active_c.id)

    # Complete the campaign — should fall back
    active_c.status = CampaignStatus.completed
    await db.flush()

    campaign_id = await find_campaign_for_subscription(db, sub)
    assert str(campaign_id) == str(fallback_c.id)


# ---------------------------------------------------------------------------
# Reallocation
# ---------------------------------------------------------------------------


async def test_reallocate_on_campaign_completed(
    db: AsyncSession, user: User, foundation: Foundation
):
    """Subscriptions are moved to a new campaign when their campaign completes."""
    old_c = await create_campaign(db, foundation, title="Old", urgency_level=3)
    new_c = await create_campaign(db, foundation, title="New", urgency_level=5)

    sub = await create_subscription(
        db,
        user,
        allocation_strategy=AllocationStrategy.specific_campaign,
        campaign_id=old_c.id,
        foundation_id=foundation.id,
        status=SubscriptionStatus.active,
    )

    old_c.status = CampaignStatus.completed
    await db.flush()

    count = await reallocate_campaign_subscriptions(
        db, old_c.id, AllocationChangeReason.campaign_completed.value
    )

    assert count == 1
    await db.refresh(sub)
    assert str(sub.campaign_id) == str(new_c.id)


async def test_reallocate_no_campaigns_pauses(db: AsyncSession, user: User):
    """Subscription is paused when no campaigns are available for reallocation."""
    f = await create_foundation(db, status=FoundationStatus.active)
    only_c = await create_campaign(db, f, title="Only")

    sub = await create_subscription(
        db,
        user,
        allocation_strategy=AllocationStrategy.specific_campaign,
        campaign_id=only_c.id,
        foundation_id=f.id,
        status=SubscriptionStatus.active,
    )

    # Complete the only campaign — no fallback available
    only_c.status = CampaignStatus.completed
    await db.flush()

    new_id = await reallocate_subscription(
        db, sub, AllocationChangeReason.campaign_completed
    )

    assert new_id is None
    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.paused
    assert sub.paused_reason == PausedReason.no_campaigns


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------


async def test_streak_update(db: AsyncSession, user: User):
    """First payment today sets streak to 1."""
    await update_user_streak(db, user.id)
    await db.refresh(user)

    assert user.current_streak_days == 1
    assert user.last_streak_date == dt.date.today()


async def test_streak_reset(db: AsyncSession):
    """Streak resets to 1 if last payment was more than 1 day ago."""
    user = await create_user(db)

    # Fake a streak from 3 days ago
    await db.execute(
        text("""
            UPDATE users
            SET current_streak_days = 5, last_streak_date = :old_date
            WHERE id = :uid
        """),
        {"old_date": dt.date.today() - dt.timedelta(days=3), "uid": user.id},
    )
    await db.flush()

    await update_user_streak(db, user.id)
    await db.refresh(user)

    assert user.current_streak_days == 1


# ---------------------------------------------------------------------------
# User impact counters
# ---------------------------------------------------------------------------


async def test_user_impact_counters(db: AsyncSession, user: User):
    """total_donated and total_donations_count are incremented atomically."""
    await update_user_impact(db, user.id, 5000)
    await update_user_impact(db, user.id, 3000)

    await db.refresh(user)
    assert user.total_donated_kopecks == 8000
    assert user.total_donations_count == 2
