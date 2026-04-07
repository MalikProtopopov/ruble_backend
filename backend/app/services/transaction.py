"""Transaction service — list and detail."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.models import Campaign, Foundation, Subscription, Transaction


def _serialize_transaction(txn, campaign, foundation) -> dict:
    """Serialize transaction with campaign and foundation data."""
    return {
        "id": txn.id,
        "subscription_id": txn.subscription_id,
        "campaign_id": txn.campaign_id,
        "campaign_title": campaign.title if campaign else None,
        "campaign_status": campaign.status.value if campaign else None,
        "campaign_thumbnail_url": campaign.thumbnail_url if campaign else None,
        "foundation_name": foundation.name if foundation else None,
        "amount_kopecks": txn.amount_kopecks,
        "status": txn.status.value if hasattr(txn.status, "value") else txn.status,
        "skipped_reason": txn.skipped_reason.value if txn.skipped_reason and hasattr(txn.skipped_reason, "value") else txn.skipped_reason,
        "created_at": txn.created_at,
    }


def _serialize_transaction_detail(txn, campaign, foundation) -> dict:
    """Serialize transaction detail with full data."""
    result = _serialize_transaction(txn, campaign, foundation)
    result["foundation_id"] = campaign.foundation_id if campaign else None
    result["foundation_logo_url"] = foundation.logo_url if foundation else None
    result["platform_fee_kopecks"] = txn.platform_fee_kopecks
    result["nco_amount_kopecks"] = txn.nco_amount_kopecks
    result["cancellation_reason"] = txn.cancellation_reason
    result["attempt_number"] = txn.attempt_number
    result["next_retry_at"] = txn.next_retry_at
    return result


async def list_transactions(
    session: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    cursor: str | None = None,
    status: str | None = None,
    campaign_id: UUID | None = None,
    subscription_id: UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    query = (
        select(Transaction, Campaign, Foundation)
        .join(Subscription, Transaction.subscription_id == Subscription.id)
        .outerjoin(Campaign, Transaction.campaign_id == Campaign.id)
        .outerjoin(Foundation, Campaign.foundation_id == Foundation.id)
        .where(Subscription.user_id == user_id)
        .order_by(Transaction.created_at.desc())
    )
    if status:
        query = query.where(Transaction.status == status)
    if campaign_id:
        query = query.where(Transaction.campaign_id == campaign_id)
    if subscription_id:
        query = query.where(Transaction.subscription_id == subscription_id)
    if date_from:
        query = query.where(Transaction.created_at >= date_from)
    if date_to:
        query = query.where(Transaction.created_at <= date_to)
    if cursor:
        cursor_data = decode_cursor(cursor)
        query = query.where(Transaction.created_at < cursor_data["created_at"])

    result = await session.execute(query.limit(limit + 1))
    rows = result.all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    data = [_serialize_transaction(t, c, f) for t, c, f in rows]

    next_cursor = None
    if has_more and rows:
        next_cursor = encode_cursor({"created_at": rows[-1][0].created_at.isoformat()})

    return {"data": data, "has_more": has_more, "next_cursor": next_cursor}


async def get_transaction_detail(session: AsyncSession, user_id: UUID, transaction_id: UUID) -> dict:
    result = await session.execute(
        select(Transaction, Campaign, Foundation)
        .join(Subscription, Transaction.subscription_id == Subscription.id)
        .outerjoin(Campaign, Transaction.campaign_id == Campaign.id)
        .outerjoin(Foundation, Campaign.foundation_id == Foundation.id)
        .where(Transaction.id == transaction_id, Subscription.user_id == user_id)
    )
    row = result.first()
    if row is None:
        raise NotFoundError("Транзакция не найдена")
    txn, campaign, foundation = row
    return _serialize_transaction_detail(txn, campaign, foundation)
