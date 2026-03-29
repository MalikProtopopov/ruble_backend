"""Payout repository."""

import datetime as dt
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams, decode_cursor, encode_cursor
from app.models import Donation, Foundation, PayoutRecord, Transaction
from app.models.base import DonationStatus, TransactionStatus, uuid7


async def list_payouts(
    session: AsyncSession, pagination: PaginationParams, *,
    foundation_id: UUID | None = None, period_from: dt.date | None = None, period_to: dt.date | None = None,
) -> dict:
    """List payouts with foundation name join.

    Returns {"items": [{"payout": PayoutRecord, "foundation_name": str}, ...],
             "next_cursor": ..., "has_more": ...}
    """
    query = select(PayoutRecord, Foundation.name).join(
        Foundation, PayoutRecord.foundation_id == Foundation.id
    )
    if foundation_id:
        query = query.where(PayoutRecord.foundation_id == foundation_id)
    if period_from:
        query = query.where(PayoutRecord.period_from >= period_from)
    if period_to:
        query = query.where(PayoutRecord.period_to <= period_to)

    if pagination.cursor:
        cursor_data = decode_cursor(pagination.cursor)
        query = query.where(PayoutRecord.id < UUID(cursor_data["id"]))

    query = query.order_by(desc(PayoutRecord.id)).limit(pagination.limit + 1)
    result = await session.execute(query)
    rows = list(result.all())

    has_more = len(rows) > pagination.limit
    if has_more:
        rows = rows[: pagination.limit]

    next_cursor = encode_cursor({"id": str(rows[-1][0].id)}) if has_more and rows else None
    items = [{"payout": payout, "foundation_name": fname} for payout, fname in rows]
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


async def create(session: AsyncSession, **kwargs) -> PayoutRecord:
    payout = PayoutRecord(id=uuid7(), **kwargs)
    session.add(payout)
    await session.flush()
    return payout


async def get_balance_by_foundation(
    session: AsyncSession, *, period_from: dt.date | None = None, period_to: dt.date | None = None,
) -> list[dict]:
    """Calculate due balance for each foundation.

    Iterates over all foundations and sums NCO from donations, transactions,
    and already-paid payouts. Matches the logic in admin/payouts.py balance endpoint.
    """
    foundations_result = await session.execute(select(Foundation))
    foundations = list(foundations_result.scalars().all())

    balances = []
    for f in foundations:
        # Sum nco_amount from successful donations
        don_filters = [
            Donation.foundation_id == f.id,
            Donation.status == DonationStatus.success,
        ]
        if period_from:
            don_filters.append(Donation.created_at >= period_from)
        if period_to:
            don_filters.append(Donation.created_at <= period_to)

        don_result = await session.execute(
            select(func.coalesce(func.sum(Donation.nco_amount_kopecks), 0)).where(*don_filters)
        )
        don_nco = don_result.scalar()

        # Sum nco_amount from successful transactions
        txn_filters = [
            Transaction.foundation_id == f.id,
            Transaction.status == TransactionStatus.success,
        ]
        if period_from:
            txn_filters.append(Transaction.created_at >= period_from)
        if period_to:
            txn_filters.append(Transaction.created_at <= period_to)

        txn_result = await session.execute(
            select(func.coalesce(func.sum(Transaction.nco_amount_kopecks), 0)).where(*txn_filters)
        )
        txn_nco = txn_result.scalar()

        total_nco = don_nco + txn_nco

        # Sum payouts already made
        payout_filters = [PayoutRecord.foundation_id == f.id]
        if period_from:
            payout_filters.append(PayoutRecord.period_from >= period_from)
        if period_to:
            payout_filters.append(PayoutRecord.period_to <= period_to)

        payout_result = await session.execute(
            select(func.coalesce(func.sum(PayoutRecord.amount_kopecks), 0)).where(*payout_filters)
        )
        total_paid = payout_result.scalar()

        due = total_nco - total_paid

        balances.append({
            "foundation_id": str(f.id),
            "foundation_name": f.name,
            "total_nco_kopecks": total_nco,
            "total_paid_kopecks": total_paid,
            "due_kopecks": due,
        })

    return balances
