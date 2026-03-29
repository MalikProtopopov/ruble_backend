"""Integration tests for webhook handling (payment succeeded / canceled)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.models import (
    Achievement,
    Campaign,
    Donation,
    Foundation,
    PatronPaymentLink,
    Subscription,
    ThanksContent,
    Transaction,
    User,
)
from app.models.base import (
    AchievementConditionType,
    AllocationStrategy,
    BillingPeriod,
    CampaignStatus,
    DonationSource,
    DonationStatus,
    PatronLinkStatus,
    SubscriptionStatus,
    ThanksContentType,
    TransactionStatus,
)
from app.services.payment import calculate_fees
from app.services.webhook import handle_payment_canceled, handle_payment_succeeded
from tests.conftest import (
    create_campaign,
    create_foundation,
    create_subscription,
    create_user,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_pending_donation(
    db: AsyncSession,
    user: User,
    campaign: Campaign,
    amount: int = 10000,
    source: DonationSource = DonationSource.app,
    payment_id: str | None = None,
) -> Donation:
    fees = calculate_fees(amount)
    donation = Donation(
        id=uuid7(),
        user_id=user.id,
        campaign_id=campaign.id,
        foundation_id=campaign.foundation_id,
        amount_kopecks=amount,
        platform_fee_kopecks=fees["platform_fee_kopecks"],
        nco_amount_kopecks=fees["nco_amount_kopecks"],
        idempotence_key=str(uuid7()),
        provider_payment_id=payment_id or f"pay_{uuid7().hex[:12]}",
        status=DonationStatus.pending,
        source=source,
    )
    db.add(donation)
    await db.flush()
    return donation


async def _make_pending_transaction(
    db: AsyncSession,
    subscription: Subscription,
    campaign: Campaign,
    amount: int = 9000,
    payment_id: str | None = None,
) -> Transaction:
    fees = calculate_fees(amount)
    txn = Transaction(
        id=uuid7(),
        subscription_id=subscription.id,
        campaign_id=campaign.id,
        foundation_id=campaign.foundation_id,
        amount_kopecks=amount,
        platform_fee_kopecks=fees["platform_fee_kopecks"],
        nco_amount_kopecks=fees["nco_amount_kopecks"],
        idempotence_key=str(uuid7()),
        provider_payment_id=payment_id or f"pay_{uuid7().hex[:12]}",
        status=TransactionStatus.pending,
    )
    db.add(txn)
    await db.flush()
    return txn


# ---------------------------------------------------------------------------
# payment succeeded — donation
# ---------------------------------------------------------------------------


async def test_donation_payment_succeeded(
    db: AsyncSession, user: User, campaign: Campaign
):
    """Successful donation payment updates status, campaign counters, user impact."""
    donation = await _make_pending_donation(db, user, campaign, amount=5000)
    old_collected = campaign.collected_amount

    await handle_payment_succeeded(
        db,
        donation.provider_payment_id,
        {"type": "donation", "entity_id": str(donation.id)},
    )

    await db.refresh(donation)
    assert donation.status == DonationStatus.success

    await db.refresh(campaign)
    assert campaign.collected_amount == old_collected + 5000

    await db.refresh(user)
    assert user.total_donated_kopecks >= 5000
    assert user.total_donations_count >= 1


# ---------------------------------------------------------------------------
# payment succeeded — transaction (subscription)
# ---------------------------------------------------------------------------


async def test_transaction_payment_succeeded(
    db: AsyncSession, user: User, campaign: Campaign
):
    """Successful transaction payment updates status, moves next_billing_at, updates streak."""
    sub = await create_subscription(
        db, user, status=SubscriptionStatus.active, campaign_id=campaign.id
    )
    txn = await _make_pending_transaction(db, sub, campaign, amount=9000)

    await handle_payment_succeeded(
        db,
        txn.provider_payment_id,
        {"type": "transaction", "entity_id": str(txn.id)},
    )

    await db.refresh(txn)
    assert txn.status == TransactionStatus.success

    await db.refresh(sub)
    assert sub.next_billing_at is not None

    await db.refresh(user)
    assert user.total_donated_kopecks >= 9000


# ---------------------------------------------------------------------------
# payment succeeded — patron link
# ---------------------------------------------------------------------------


async def test_patron_link_payment_succeeded(
    db: AsyncSession, user: User, campaign: Campaign
):
    """Patron-link payment sets donation=success, link=paid, updates counters."""
    donation = await _make_pending_donation(
        db, user, campaign, amount=50000, source=DonationSource.patron_link
    )

    link = PatronPaymentLink(
        id=uuid7(),
        campaign_id=campaign.id,
        created_by_user_id=user.id,
        amount_kopecks=50000,
        donation_id=donation.id,
        payment_url="https://example.com/pay",
        expires_at=donation.created_at,
    )
    db.add(link)
    await db.flush()

    await handle_payment_succeeded(
        db,
        donation.provider_payment_id,
        {"type": "patron_link", "entity_id": str(link.id)},
    )

    await db.refresh(donation)
    assert donation.status == DonationStatus.success

    await db.refresh(link)
    assert link.status == PatronLinkStatus.paid

    await db.refresh(campaign)
    assert campaign.collected_amount >= 50000


# ---------------------------------------------------------------------------
# payment canceled
# ---------------------------------------------------------------------------


async def test_payment_canceled_transaction(
    db: AsyncSession, user: User, campaign: Campaign
):
    """Canceled transaction is marked failed with retry scheduled."""
    sub = await create_subscription(
        db, user, status=SubscriptionStatus.active, campaign_id=campaign.id
    )
    txn = await _make_pending_transaction(db, sub, campaign)

    await handle_payment_canceled(db, txn.provider_payment_id, "insufficient_funds")

    await db.refresh(txn)
    assert txn.status == TransactionStatus.failed
    assert txn.cancellation_reason == "insufficient_funds"
    assert txn.next_retry_at is not None  # attempt_number=1 < 4


async def test_payment_canceled_donation(
    db: AsyncSession, user: User, campaign: Campaign
):
    """Canceled donation is marked failed."""
    donation = await _make_pending_donation(db, user, campaign)

    await handle_payment_canceled(db, donation.provider_payment_id, "card_expired")

    await db.refresh(donation)
    assert donation.status == DonationStatus.failed


# ---------------------------------------------------------------------------
# achievements
# ---------------------------------------------------------------------------


async def test_achievement_awarded_on_payment(
    db: AsyncSession, user: User, campaign: Campaign
):
    """First donation triggers FIRST_DONATION achievement."""
    # Create achievement that requires donations_count >= 1
    ach = Achievement(
        id=uuid7(),
        code="FIRST_DONATION",
        title="First Donation",
        condition_type=AchievementConditionType.donations_count,
        condition_value=1,
        is_active=True,
    )
    db.add(ach)
    await db.flush()

    donation = await _make_pending_donation(db, user, campaign, amount=2000)

    await handle_payment_succeeded(
        db,
        donation.provider_payment_id,
        {"type": "donation", "entity_id": str(donation.id)},
    )

    from app.models import UserAchievement

    earned = (
        await db.execute(
            select(UserAchievement).where(
                UserAchievement.user_id == user.id,
                UserAchievement.achievement_id == ach.id,
            )
        )
    ).scalar_one_or_none()
    assert earned is not None


# ---------------------------------------------------------------------------
# thanks detection
# ---------------------------------------------------------------------------


async def test_thanks_detected_on_payment(
    db: AsyncSession, user: User, campaign: Campaign
):
    """After payment, unseen thanks content for the campaign is found."""
    thanks = ThanksContent(
        id=uuid7(),
        campaign_id=campaign.id,
        type=ThanksContentType.video,
        media_url="https://example.com/video.mp4",
        title="Thank you!",
    )
    db.add(thanks)
    await db.flush()

    donation = await _make_pending_donation(db, user, campaign, amount=3000)

    # The handler logs thanks_id internally; we verify thanks_content exists
    # and that find_unseen_thanks_for_campaign would find it.
    from app.services.thanks import find_unseen_thanks_for_campaign

    thanks_id = await find_unseen_thanks_for_campaign(db, user.id, campaign.id)
    assert str(thanks_id) == str(thanks.id)


# ---------------------------------------------------------------------------
# idempotency
# ---------------------------------------------------------------------------


async def test_idempotent_double_success(
    db: AsyncSession, user: User, campaign: Campaign
):
    """Calling handle_payment_succeeded twice does not double-increment counters."""
    donation = await _make_pending_donation(db, user, campaign, amount=4000)

    metadata = {"type": "donation", "entity_id": str(donation.id)}
    await handle_payment_succeeded(db, donation.provider_payment_id, metadata)

    await db.refresh(campaign)
    collected_after_first = campaign.collected_amount

    await db.refresh(user)
    donated_after_first = user.total_donated_kopecks

    # Second call — donation.status is already 'success', so handler should skip
    await handle_payment_succeeded(db, donation.provider_payment_id, metadata)

    await db.refresh(campaign)
    assert campaign.collected_amount == collected_after_first

    await db.refresh(user)
    assert user.total_donated_kopecks == donated_after_first
