"""Integration tests for the subscription lifecycle."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.models import Campaign, Subscription, Transaction, User
from app.models.base import (
    AllocationStrategy,
    BillingPeriod,
    CampaignStatus,
    SubscriptionStatus,
    TransactionStatus,
)
from app.services.subscription import (
    bind_card,
    cancel_subscription,
    create_subscription,
    list_subscriptions,
    pause_subscription,
    resume_subscription,
    update_subscription,
)
from tests.conftest import (
    create_campaign,
    create_foundation,
    create_subscription as factory_subscription,
    create_user,
)


def _sub_data(**overrides) -> dict:
    base = {
        "amount_kopecks": 300,
        "billing_period": "monthly",
        "allocation_strategy": "platform_pool",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# create_subscription
# ---------------------------------------------------------------------------


async def test_create_subscription_success(db: AsyncSession, user: User):
    """Subscription is created with pending_payment_method status."""
    sub = await create_subscription(db, user.id, _sub_data())

    assert sub.status == SubscriptionStatus.pending_payment_method
    assert sub.amount_kopecks == 300
    assert sub.allocation_strategy == AllocationStrategy.platform_pool


async def test_create_subscription_invalid_amount(db: AsyncSession, user: User):
    """Non-standard amount raises INVALID_AMOUNT."""
    with pytest.raises(BusinessLogicError) as exc_info:
        await create_subscription(db, user.id, _sub_data(amount_kopecks=250))

    assert exc_info.value.code == "INVALID_AMOUNT"


async def test_create_subscription_limit_exceeded(db: AsyncSession, user: User):
    """6th subscription raises SUBSCRIPTION_LIMIT_EXCEEDED."""
    for _ in range(5):
        await factory_subscription(db, user, amount_kopecks=100)

    with pytest.raises(BusinessLogicError) as exc_info:
        await create_subscription(db, user.id, _sub_data(amount_kopecks=100))

    assert exc_info.value.code == "SUBSCRIPTION_LIMIT_EXCEEDED"


async def test_create_subscription_specific_campaign(
    db: AsyncSession, user: User, campaign: Campaign
):
    """Subscription with specific_campaign strategy stores campaign_id."""
    sub = await create_subscription(
        db,
        user.id,
        _sub_data(
            allocation_strategy="specific_campaign",
            campaign_id=campaign.id,
        ),
    )
    assert sub.campaign_id == campaign.id


async def test_create_subscription_specific_campaign_inactive(
    db: AsyncSession, user: User, foundation
):
    """specific_campaign with inactive campaign raises CAMPAIGN_NOT_ACTIVE."""
    completed = await create_campaign(db, foundation, status=CampaignStatus.completed)

    with pytest.raises(BusinessLogicError) as exc_info:
        await create_subscription(
            db,
            user.id,
            _sub_data(
                allocation_strategy="specific_campaign",
                campaign_id=completed.id,
            ),
        )

    assert exc_info.value.code == "CAMPAIGN_NOT_ACTIVE"


# ---------------------------------------------------------------------------
# bind_card
# ---------------------------------------------------------------------------


async def test_bind_card_success(db: AsyncSession, user: User):
    """bind_card creates a Transaction and returns payment_url."""
    sub = await create_subscription(db, user.id, _sub_data())

    result = await bind_card(db, sub.id, user.id)

    assert result["payment_url"]
    assert result["subscription_id"] == sub.id
    # Transaction should exist
    txn = (
        await db.execute(
            select(Transaction).where(Transaction.subscription_id == sub.id)
        )
    ).scalar_one()
    assert txn.status == TransactionStatus.pending


async def test_bind_card_already_active(db: AsyncSession, user: User):
    """bind_card on an active subscription raises SUBSCRIPTION_ALREADY_ACTIVE."""
    sub = await factory_subscription(db, user, status=SubscriptionStatus.active)

    with pytest.raises(BusinessLogicError) as exc_info:
        await bind_card(db, sub.id, user.id)

    assert exc_info.value.code == "SUBSCRIPTION_ALREADY_ACTIVE"


# ---------------------------------------------------------------------------
# pause / resume / cancel
# ---------------------------------------------------------------------------


async def test_pause_subscription_success(db: AsyncSession, user: User):
    """Pausing sets status=paused and clears next_billing_at."""
    sub = await factory_subscription(db, user, status=SubscriptionStatus.active)

    paused = await pause_subscription(db, sub.id, user.id)

    assert paused.status == SubscriptionStatus.paused
    assert paused.next_billing_at is None
    assert paused.paused_at is not None


async def test_pause_not_active(db: AsyncSession, user: User):
    """Pausing a non-active subscription raises error."""
    sub = await factory_subscription(
        db, user, status=SubscriptionStatus.pending_payment_method
    )

    with pytest.raises(BusinessLogicError) as exc_info:
        await pause_subscription(db, sub.id, user.id)

    assert exc_info.value.code == "SUBSCRIPTION_NOT_ACTIVE"


async def test_resume_subscription_success(db: AsyncSession, user: User):
    """Resuming sets status=active and schedules next_billing_at."""
    sub = await factory_subscription(db, user, status=SubscriptionStatus.active)
    await pause_subscription(db, sub.id, user.id)

    resumed = await resume_subscription(db, sub.id, user.id)

    assert resumed.status == SubscriptionStatus.active
    assert resumed.next_billing_at is not None
    assert resumed.paused_at is None


async def test_cancel_subscription(db: AsyncSession, user: User):
    """Cancelling sets status=cancelled with cancelled_at timestamp."""
    sub = await factory_subscription(db, user, status=SubscriptionStatus.active)

    await cancel_subscription(db, sub.id, user.id)
    await db.refresh(sub)

    assert sub.status == SubscriptionStatus.cancelled
    assert sub.cancelled_at is not None
    assert sub.next_billing_at is None


# ---------------------------------------------------------------------------
# update / list
# ---------------------------------------------------------------------------


async def test_update_subscription_amount(db: AsyncSession, user: User):
    """Updating amount_kopecks persists the change."""
    sub = await factory_subscription(db, user, amount_kopecks=300)

    updated = await update_subscription(db, sub.id, user.id, {"amount_kopecks": 500})

    assert updated.amount_kopecks == 500


async def test_list_subscriptions(db: AsyncSession, user: User):
    """list_subscriptions returns active/paused/pending but not cancelled."""
    s_active = await factory_subscription(db, user, status=SubscriptionStatus.active, amount_kopecks=100)
    s_paused = await factory_subscription(db, user, status=SubscriptionStatus.active, amount_kopecks=300)
    await pause_subscription(db, s_paused.id, user.id)
    s_pending = await create_subscription(db, user.id, _sub_data(amount_kopecks=500))
    s_cancelled = await factory_subscription(db, user, status=SubscriptionStatus.active, amount_kopecks=1000)
    await cancel_subscription(db, s_cancelled.id, user.id)

    subs = await list_subscriptions(db, user.id)

    ids = {s.id for s in subs}
    assert s_active.id in ids
    assert s_paused.id in ids
    assert s_pending.id in ids
    assert s_cancelled.id not in ids
