"""Saved payment method service."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models import PaymentMethod
from app.models.base import uuid7

logger = get_logger(__name__)


async def list_for_user(session: AsyncSession, user_id: UUID) -> list[PaymentMethod]:
    result = await session.execute(
        select(PaymentMethod)
        .where(PaymentMethod.user_id == user_id, PaymentMethod.is_deleted == False)  # noqa: E712
        .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
    )
    return list(result.scalars().all())


async def get_for_user(session: AsyncSession, pm_id: UUID, user_id: UUID) -> PaymentMethod:
    result = await session.execute(
        select(PaymentMethod).where(
            PaymentMethod.id == pm_id,
            PaymentMethod.user_id == user_id,
            PaymentMethod.is_deleted == False,  # noqa: E712
        )
    )
    pm = result.scalar_one_or_none()
    if pm is None:
        raise NotFoundError("Способ оплаты не найден")
    return pm


async def save_from_yookassa(
    session: AsyncSession,
    *,
    user_id: UUID,
    provider_pm_id: str,
    card_last4: str | None = None,
    card_type: str | None = None,
    title: str | None = None,
) -> PaymentMethod:
    """Persist a YooKassa-saved payment method after a successful donation.

    Idempotent: if the same provider_pm_id already exists for this user, returns it.
    """
    existing_result = await session.execute(
        select(PaymentMethod).where(
            PaymentMethod.provider == "yookassa",
            PaymentMethod.provider_pm_id == provider_pm_id,
            PaymentMethod.is_deleted == False,  # noqa: E712
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing

    # If the user has no other payment methods, make this one default.
    any_result = await session.execute(
        select(PaymentMethod.id).where(
            PaymentMethod.user_id == user_id,
            PaymentMethod.is_deleted == False,  # noqa: E712
        ).limit(1)
    )
    is_first = any_result.scalar_one_or_none() is None

    pm = PaymentMethod(
        id=uuid7(),
        user_id=user_id,
        provider="yookassa",
        provider_pm_id=provider_pm_id,
        card_last4=card_last4,
        card_type=card_type,
        title=title,
        is_default=is_first,
    )
    session.add(pm)
    await session.flush()
    logger.info("payment_method_saved", user_id=str(user_id), pm_id=str(pm.id))
    return pm


async def delete_for_user(session: AsyncSession, pm_id: UUID, user_id: UUID) -> None:
    pm = await get_for_user(session, pm_id, user_id)
    pm.is_deleted = True
    was_default = pm.is_default
    pm.is_default = False
    await session.flush()

    if was_default:
        # Promote another method to default, if any.
        next_result = await session.execute(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == user_id, PaymentMethod.is_deleted == False)  # noqa: E712
            .order_by(PaymentMethod.created_at.desc())
            .limit(1)
        )
        next_pm = next_result.scalar_one_or_none()
        if next_pm is not None:
            next_pm.is_default = True
            await session.flush()


async def set_default_for_user(session: AsyncSession, pm_id: UUID, user_id: UUID) -> PaymentMethod:
    pm = await get_for_user(session, pm_id, user_id)
    await session.execute(
        update(PaymentMethod)
        .where(PaymentMethod.user_id == user_id, PaymentMethod.id != pm.id)
        .values(is_default=False)
    )
    pm.is_default = True
    await session.flush()
    return pm
