"""Regression tests for billing allocation of pool subscriptions.

Covers the §9.1a fix: recurring billing must resolve the target campaign at
charge time (specific/foundation/platform pools), and record a `skipped`
transaction without charging when no active campaign is available.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction, User
from app.models.base import (
    AllocationStrategy,
    CampaignStatus,
    SkipReason,
    SubscriptionStatus,
    TransactionStatus,
)
from app.tasks.billing import _charge_subscription
from tests.conftest import (
    create_campaign,
    create_foundation,
    create_subscription as factory_subscription,
)


async def _active_pool_sub(db: AsyncSession, user: User):
    sub = await factory_subscription(
        db,
        user,
        allocation_strategy=AllocationStrategy.platform_pool,
        status=SubscriptionStatus.active,
    )
    sub.payment_method_id = "test-pm-id"
    await db.flush()
    return sub


async def test_pool_billing_allocates_to_active_campaign(db: AsyncSession, user: User):
    """A platform_pool charge is allocated to an active campaign (was NULL before the fix)."""
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation, status=CampaignStatus.active)
    sub = await _active_pool_sub(db, user)

    await _charge_subscription(db, sub)

    rows = (
        await db.execute(select(Transaction).where(Transaction.subscription_id == sub.id))
    ).scalars().all()
    assert len(rows) == 1
    txn = rows[0]
    assert txn.status == TransactionStatus.pending
    assert txn.campaign_id == campaign.id
    assert txn.provider_payment_id is not None  # charge was attempted


async def test_pool_billing_skips_when_no_active_campaign(db: AsyncSession, user: User):
    """No active campaign → skipped transaction, no charge, next attempt rescheduled."""
    foundation = await create_foundation(db)
    await create_campaign(db, foundation, status=CampaignStatus.draft)  # nothing active
    sub = await _active_pool_sub(db, user)

    await _charge_subscription(db, sub)

    rows = (
        await db.execute(select(Transaction).where(Transaction.subscription_id == sub.id))
    ).scalars().all()
    assert len(rows) == 1
    txn = rows[0]
    assert txn.status == TransactionStatus.skipped
    assert txn.skipped_reason == SkipReason.no_active_campaigns
    assert txn.campaign_id is None
    assert txn.provider_payment_id is None  # no money taken
    assert sub.next_billing_at is not None  # rescheduled for next period
