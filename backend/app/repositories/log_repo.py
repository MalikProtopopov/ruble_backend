"""Log repository for allocation changes and notification logs."""

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams, decode_cursor, encode_cursor
from app.models import AllocationChange, Campaign, NotificationLog
from app.repositories.base import cursor_paginate


async def list_allocation_logs(
    session: AsyncSession, pagination: PaginationParams, *,
    subscription_id: UUID | None = None, reason: str | None = None,
) -> dict:
    """List allocation change logs with campaign title joins.

    Returns {"items": [...dicts...], "next_cursor": ..., "has_more": ...}
    Because of the complex join, items are pre-serialized dicts (not ORM objects).
    """
    from_campaign = Campaign.__table__.alias("from_campaign")
    to_campaign = Campaign.__table__.alias("to_campaign")

    query = (
        select(
            AllocationChange,
            from_campaign.c.title.label("from_campaign_title"),
            to_campaign.c.title.label("to_campaign_title"),
        )
        .outerjoin(from_campaign, AllocationChange.from_campaign_id == from_campaign.c.id)
        .outerjoin(to_campaign, AllocationChange.to_campaign_id == to_campaign.c.id)
    )

    if subscription_id:
        query = query.where(AllocationChange.subscription_id == subscription_id)
    if reason:
        query = query.where(AllocationChange.reason == reason)

    if pagination.cursor:
        cursor_data = decode_cursor(pagination.cursor)
        query = query.where(AllocationChange.id < UUID(cursor_data["id"]))

    query = query.order_by(desc(AllocationChange.id)).limit(pagination.limit + 1)
    result = await session.execute(query)
    rows = list(result.all())

    has_more = len(rows) > pagination.limit
    if has_more:
        rows = rows[: pagination.limit]

    items = []
    for ac, from_title, to_title in rows:
        items.append({
            "id": str(ac.id),
            "subscription_id": str(ac.subscription_id),
            "from_campaign_id": str(ac.from_campaign_id) if ac.from_campaign_id else None,
            "from_campaign_title": from_title,
            "to_campaign_id": str(ac.to_campaign_id) if ac.to_campaign_id else None,
            "to_campaign_title": to_title,
            "reason": ac.reason.value,
            "notified_at": ac.notified_at.isoformat() if ac.notified_at else None,
            "created_at": ac.created_at.isoformat(),
        })

    next_cursor = encode_cursor({"id": items[-1]["id"]}) if has_more and items else None
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


async def list_notification_logs(
    session: AsyncSession, pagination: PaginationParams, *,
    user_id: UUID | None = None, notification_type: str | None = None, status: str | None = None,
) -> dict:
    query = select(NotificationLog)
    if user_id:
        query = query.where(NotificationLog.user_id == user_id)
    if notification_type:
        query = query.where(NotificationLog.notification_type == notification_type)
    if status:
        query = query.where(NotificationLog.status == status)
    return await cursor_paginate(session, query, NotificationLog, pagination)
