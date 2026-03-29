"""Base repository utilities — cursor pagination, common query helpers."""

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.pagination import PaginationParams, decode_cursor, encode_cursor, paginated_response


async def cursor_paginate(
    session: AsyncSession,
    query: Select,
    model,
    pagination: PaginationParams,
    id_column=None,
) -> dict:
    """Execute a query with cursor-based pagination.

    Returns dict: {"items": [...], "next_cursor": ..., "has_more": ...}

    Args:
        query: Base SELECT query (with filters already applied, WITHOUT order/limit)
        model: SQLAlchemy model class (used for .id column)
        pagination: PaginationParams with limit and cursor
        id_column: Override for the ID column (default: model.id)
    """
    col = id_column or model.id

    if pagination.cursor:
        cursor_data = decode_cursor(pagination.cursor)
        query = query.where(col < UUID(cursor_data["id"]))

    query = query.order_by(desc(col)).limit(pagination.limit + 1)
    result = await session.execute(query)
    items = list(result.unique().scalars().all())

    has_more = len(items) > pagination.limit
    if has_more:
        items = items[: pagination.limit]

    next_cursor = encode_cursor({"id": str(items[-1].id)}) if has_more and items else None
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}
