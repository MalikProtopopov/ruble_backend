"""Foundation repository."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.models import Foundation
from app.models.base import uuid7
from app.repositories.base import cursor_paginate


async def get_by_id(session: AsyncSession, foundation_id: UUID) -> Foundation | None:
    result = await session.execute(select(Foundation).where(Foundation.id == foundation_id))
    return result.scalar_one_or_none()


async def get_by_inn(session: AsyncSession, inn: str) -> Foundation | None:
    result = await session.execute(select(Foundation).where(Foundation.inn == inn))
    return result.scalar_one_or_none()


async def list_admin(
    session: AsyncSession, pagination: PaginationParams, *, status: str | None = None, search: str | None = None,
) -> dict:
    query = select(Foundation)
    if status:
        query = query.where(Foundation.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Foundation.name.ilike(pattern), Foundation.legal_name.ilike(pattern), Foundation.inn.ilike(pattern)))
    return await cursor_paginate(session, query, Foundation, pagination)


async def create(session: AsyncSession, **kwargs) -> Foundation:
    foundation = Foundation(id=uuid7(), **kwargs)
    session.add(foundation)
    await session.flush()
    await session.refresh(foundation)
    return foundation


async def update(session: AsyncSession, foundation: Foundation, data: dict) -> Foundation:
    for field, value in data.items():
        setattr(foundation, field, value)
    await session.flush()
    await session.refresh(foundation)
    return foundation
