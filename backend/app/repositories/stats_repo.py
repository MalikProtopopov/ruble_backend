"""Statistics repository — aggregation queries for the admin dashboard."""

import datetime as dt
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign, Donation, Subscription, Transaction, User
from app.models.base import DonationStatus, SubscriptionStatus, TransactionStatus


async def get_overview_stats(
    session: AsyncSession, period_from: dt.date | None = None, period_to: dt.date | None = None,
) -> dict:
    """Aggregate platform-wide stats for the admin overview endpoint."""

    def _period_filter(model_created_at):
        conditions = []
        if period_from:
            conditions.append(model_created_at >= period_from)
        if period_to:
            conditions.append(model_created_at <= period_to)
        return conditions

    # GMV from transactions (success)
    txn_filters = [Transaction.status == TransactionStatus.success] + _period_filter(Transaction.created_at)
    txn_gmv = await session.execute(
        select(
            func.coalesce(func.sum(Transaction.amount_kopecks), 0),
            func.coalesce(func.sum(Transaction.platform_fee_kopecks), 0),
        ).where(*txn_filters)
    )
    txn_row = txn_gmv.one()

    # GMV from donations (success)
    don_filters = [Donation.status == DonationStatus.success] + _period_filter(Donation.created_at)
    don_gmv = await session.execute(
        select(
            func.coalesce(func.sum(Donation.amount_kopecks), 0),
            func.coalesce(func.sum(Donation.platform_fee_kopecks), 0),
        ).where(*don_filters)
    )
    don_row = don_gmv.one()

    gmv = txn_row[0] + don_row[0]
    platform_fee = txn_row[1] + don_row[1]

    # Active subscriptions count
    active_subs_result = await session.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.status == SubscriptionStatus.active,
            Subscription.is_deleted == False,
        )
    )
    active_subscriptions = active_subs_result.scalar()

    # Total donors: distinct users with at least one success donation
    total_donors_result = await session.execute(
        select(func.count(distinct(Donation.user_id))).where(
            Donation.status == DonationStatus.success,
            Donation.user_id.isnot(None),
        )
    )
    total_donors = total_donors_result.scalar()

    # New donors in period
    new_donors_filters = [User.is_deleted == False]
    if period_from:
        new_donors_filters.append(User.created_at >= period_from)
    if period_to:
        new_donors_filters.append(User.created_at <= period_to)
    new_donors_result = await session.execute(
        select(func.count()).select_from(User).where(*new_donors_filters)
    )
    new_donors_period = new_donors_result.scalar()

    # Retention: users who donated in last 30/90 days
    now = dt.date.today()
    ret_30_result = await session.execute(
        select(func.count(distinct(Donation.user_id))).where(
            Donation.status == DonationStatus.success,
            Donation.user_id.isnot(None),
            Donation.created_at >= now - dt.timedelta(days=30),
        )
    )
    retention_30d = ret_30_result.scalar()

    ret_90_result = await session.execute(
        select(func.count(distinct(Donation.user_id))).where(
            Donation.status == DonationStatus.success,
            Donation.user_id.isnot(None),
            Donation.created_at >= now - dt.timedelta(days=90),
        )
    )
    retention_90d = ret_90_result.scalar()

    return {
        "gmv_kopecks": gmv,
        "platform_fee_kopecks": platform_fee,
        "active_subscriptions": active_subscriptions,
        "total_donors": total_donors,
        "new_donors_period": new_donors_period,
        "retention_30d": retention_30d,
        "retention_90d": retention_90d,
        "total_donors_for_retention": total_donors,
    }


async def get_campaign_stats(session: AsyncSession, campaign_id: UUID) -> dict:
    """Aggregate stats for a specific campaign."""
    # Verify campaign exists and get basic info
    result = await session.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        return None

    # Donations stats
    don_result = await session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(Donation.amount_kopecks), 0),
            func.coalesce(func.sum(Donation.platform_fee_kopecks), 0),
            func.coalesce(func.sum(Donation.nco_amount_kopecks), 0),
        ).where(
            Donation.campaign_id == campaign_id,
            Donation.status == DonationStatus.success,
        )
    )
    don_row = don_result.one()

    # Transaction stats
    txn_result = await session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(Transaction.amount_kopecks), 0),
            func.coalesce(func.sum(Transaction.platform_fee_kopecks), 0),
            func.coalesce(func.sum(Transaction.nco_amount_kopecks), 0),
        ).where(
            Transaction.campaign_id == campaign_id,
            Transaction.status == TransactionStatus.success,
        )
    )
    txn_row = txn_result.one()

    # Unique donors
    unique_donors_result = await session.execute(
        select(func.count(distinct(Donation.user_id))).where(
            Donation.campaign_id == campaign_id,
            Donation.status == DonationStatus.success,
            Donation.user_id.isnot(None),
        )
    )
    unique_donors = unique_donors_result.scalar()

    # Active subscriptions targeting this campaign
    subs_result = await session.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.campaign_id == campaign_id,
            Subscription.status == SubscriptionStatus.active,
        )
    )
    active_subs = subs_result.scalar()

    return {
        "campaign_id": str(campaign_id),
        "title": campaign.title,
        "status": campaign.status.value,
        "goal_amount": campaign.goal_amount,
        "collected_amount": campaign.collected_amount,
        "donors_count": campaign.donors_count,
        "donations_count": don_row[0],
        "donations_amount_kopecks": don_row[1],
        "donations_platform_fee_kopecks": don_row[2],
        "donations_nco_amount_kopecks": don_row[3],
        "transactions_count": txn_row[0],
        "transactions_amount_kopecks": txn_row[1],
        "transactions_platform_fee_kopecks": txn_row[2],
        "transactions_nco_amount_kopecks": txn_row[3],
        "total_amount_kopecks": don_row[1] + txn_row[1],
        "unique_donors": unique_donors,
        "active_subscriptions": active_subs,
    }
