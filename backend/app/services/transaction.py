"""Transaction service — list and detail."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.models import Subscription, Transaction


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
        select(Transaction)
        .join(Subscription, Transaction.subscription_id == Subscription.id)
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
    items = list(result.scalars().all())
    has_more = len(items) > limit
    items = items[:limit]
    next_cursor = encode_cursor({"created_at": items[-1].created_at.isoformat()}) if has_more and items else None

    return {"data": items, "has_more": has_more, "next_cursor": next_cursor}


async def get_transaction_detail(session: AsyncSession, user_id: UUID, transaction_id: UUID) -> Transaction:
    result = await session.execute(
        select(Transaction)
        .join(Subscription, Transaction.subscription_id == Subscription.id)
        .where(Transaction.id == transaction_id, Subscription.user_id == user_id)
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise NotFoundError("Транзакция не найдена")
    return txn
