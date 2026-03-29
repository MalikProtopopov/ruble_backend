"""Campaign allocation strategies."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.logging import get_logger
from app.models import AllocationChange, Campaign, Subscription
from app.models.base import AllocationChangeReason, AllocationStrategy, CampaignStatus, FoundationStatus

logger = get_logger(__name__)


async def find_campaign_for_subscription(session: AsyncSession, subscription: Subscription) -> UUID | None:
    """Determine which campaign a subscription should pay to."""
    strategy = subscription.allocation_strategy

    if strategy == AllocationStrategy.specific_campaign:
        # Check if specific campaign is still active
        if subscription.campaign_id:
            result = await session.execute(
                select(Campaign.id).where(Campaign.id == subscription.campaign_id, Campaign.status == CampaignStatus.active)
            )
            if result.scalar_one_or_none():
                return subscription.campaign_id
        # Fallback to foundation_pool
        return await _find_foundation_pool(session, subscription.foundation_id)

    elif strategy == AllocationStrategy.foundation_pool:
        return await _find_foundation_pool(session, subscription.foundation_id)

    else:  # platform_pool
        return await _find_platform_pool(session)


async def _find_foundation_pool(session: AsyncSession, foundation_id: UUID | None) -> UUID | None:
    if foundation_id:
        result = await session.execute(
            select(Campaign.id)
            .where(Campaign.foundation_id == foundation_id, Campaign.status == CampaignStatus.active)
            .order_by(Campaign.urgency_level.desc(), Campaign.sort_order.asc())
            .limit(1)
        )
        campaign_id = result.scalar_one_or_none()
        if campaign_id:
            return campaign_id
    # Fallback to platform_pool
    return await _find_platform_pool(session)


async def _find_platform_pool(session: AsyncSession) -> UUID | None:
    result = await session.execute(
        text("""
            SELECT c.id FROM campaigns c
            JOIN foundations f ON f.id = c.foundation_id
            WHERE c.status = 'active' AND f.status = 'active'
            ORDER BY c.urgency_level DESC,
                     CASE WHEN c.goal_amount > 0 THEN c.collected_amount::float / c.goal_amount ELSE 0 END DESC,
                     c.sort_order ASC
            LIMIT 1
        """)
    )
    row = result.first()
    return row[0] if row else None


async def log_allocation_change(
    session: AsyncSession,
    subscription_id: UUID,
    from_campaign_id: UUID | None,
    to_campaign_id: UUID | None,
    reason: AllocationChangeReason,
) -> None:
    change = AllocationChange(
        id=uuid7(),
        subscription_id=subscription_id,
        from_campaign_id=from_campaign_id,
        to_campaign_id=to_campaign_id,
        reason=reason,
    )
    session.add(change)
    await session.flush()
    logger.info("allocation_changed", subscription_id=str(subscription_id), reason=reason.value)


async def reallocate_subscription(
    session: AsyncSession,
    subscription: Subscription,
    reason: AllocationChangeReason,
) -> UUID | None:
    """Find a new campaign for a subscription and log the change.

    Returns the new campaign_id or None if no campaign available.
    """
    old_campaign_id = subscription.campaign_id
    new_campaign_id = await find_campaign_for_subscription(session, subscription)

    if new_campaign_id and new_campaign_id != old_campaign_id:
        subscription.campaign_id = new_campaign_id
        await log_allocation_change(session, subscription.id, old_campaign_id, new_campaign_id, reason)
        logger.info(
            "subscription_reallocated",
            subscription_id=str(subscription.id),
            from_campaign=str(old_campaign_id),
            to_campaign=str(new_campaign_id),
        )
        return new_campaign_id

    if new_campaign_id is None:
        # No active campaigns available — pause subscription
        from app.models.base import PausedReason, SubscriptionStatus
        from datetime import datetime, timezone

        subscription.status = SubscriptionStatus.paused
        subscription.paused_reason = PausedReason.no_campaigns
        subscription.paused_at = datetime.now(timezone.utc)
        subscription.next_billing_at = None
        await log_allocation_change(session, subscription.id, old_campaign_id, None, reason)
        await session.flush()
        logger.warning("subscription_paused_no_campaigns", subscription_id=str(subscription.id))

    return new_campaign_id


async def reallocate_campaign_subscriptions(
    session: AsyncSession,
    campaign_id: UUID,
    reason: str,
) -> int:
    """Reallocate all active subscriptions tied to a completed/closed campaign.

    Returns the number of subscriptions reallocated.
    """
    from app.models.base import SubscriptionStatus

    reason_enum = AllocationChangeReason(reason)

    result = await session.execute(
        select(Subscription).where(
            Subscription.campaign_id == campaign_id,
            Subscription.status.in_([SubscriptionStatus.active, SubscriptionStatus.paused]),
            Subscription.is_deleted == False,
        )
    )
    subscriptions = list(result.scalars().all())

    count = 0
    for sub in subscriptions:
        new_campaign = await reallocate_subscription(session, sub, reason_enum)
        if new_campaign is not None:
            count += 1

    await session.flush()
    logger.info(
        "campaign_subscriptions_reallocated",
        campaign_id=str(campaign_id),
        reason=reason,
        count=count,
        total=len(subscriptions),
    )
    return count
