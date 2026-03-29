"""Achievement repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Achievement
from app.models.base import uuid7


async def list_all(session: AsyncSession) -> list[Achievement]:
    result = await session.execute(select(Achievement).order_by(Achievement.created_at))
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, achievement_id: UUID) -> Achievement | None:
    result = await session.execute(select(Achievement).where(Achievement.id == achievement_id))
    return result.scalar_one_or_none()


async def get_by_code(session: AsyncSession, code: str) -> Achievement | None:
    result = await session.execute(select(Achievement).where(Achievement.code == code))
    return result.scalar_one_or_none()


async def create(session: AsyncSession, **kwargs) -> Achievement:
    achievement = Achievement(id=uuid7(), **kwargs)
    session.add(achievement)
    await session.flush()
    return achievement


async def update(session: AsyncSession, achievement: Achievement, data: dict) -> Achievement:
    for field, value in data.items():
        setattr(achievement, field, value)
    await session.flush()
    return achievement
