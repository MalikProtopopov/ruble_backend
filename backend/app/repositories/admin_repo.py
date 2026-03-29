"""Admin repository."""

from uuid import UUID

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PaginationParams
from app.models import Admin, RefreshToken
from app.models.base import uuid7
from app.repositories.base import cursor_paginate


async def get_by_id(session: AsyncSession, admin_id: UUID) -> Admin | None:
    result = await session.execute(select(Admin).where(Admin.id == admin_id))
    return result.scalar_one_or_none()


async def get_by_email(session: AsyncSession, email: str) -> Admin | None:
    result = await session.execute(select(Admin).where(Admin.email == email))
    return result.scalar_one_or_none()


async def list_all(session: AsyncSession, pagination: PaginationParams, *, is_active: bool | None = None) -> dict:
    query = select(Admin)
    if is_active is not None:
        query = query.where(Admin.is_active == is_active)
    return await cursor_paginate(session, query, Admin, pagination)


async def create(session: AsyncSession, **kwargs) -> Admin:
    admin = Admin(id=uuid7(), **kwargs)
    session.add(admin)
    await session.flush()
    await session.refresh(admin)
    return admin


async def update(session: AsyncSession, admin: Admin, data: dict) -> Admin:
    for field, value in data.items():
        setattr(admin, field, value)
    await session.flush()
    await session.refresh(admin)
    return admin


async def revoke_all_tokens(session: AsyncSession, admin_id: UUID) -> None:
    await session.execute(
        sa_update(RefreshToken)
        .where(RefreshToken.admin_id == admin_id, RefreshToken.is_revoked == False)
        .values(is_revoked=True)
    )
