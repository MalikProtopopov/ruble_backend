"""Subscription service."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.models import Campaign, Foundation, Subscription, Transaction
from app.models.base import AllocationStrategy, BillingPeriod, CampaignStatus, SubscriptionStatus, TransactionStatus
from app.domain.constants import ALLOWED_SUBSCRIPTION_AMOUNTS
from app.domain.subscription import InvalidSubscriptionAmount, validate_subscription_amount
from app.domain.subscription import billing_amount
from app.services.payment import calculate_fees
from app.services.subscription_limits import check_subscription_limit


async def create_subscription(session: AsyncSession, user_id: UUID, data: dict) -> Subscription:
    amount = data["amount_kopecks"]
    try:
        validate_subscription_amount(amount)
    except InvalidSubscriptionAmount:
        raise BusinessLogicError(code="INVALID_AMOUNT", message=f"Допустимые суммы: {sorted(ALLOWED_SUBSCRIPTION_AMOUNTS)}")

    await check_subscription_limit(session, user_id)

    # Validate campaign/foundation if needed
    strategy = data["allocation_strategy"]
    campaign_id = data.get("campaign_id")
    foundation_id = data.get("foundation_id")

    if strategy == "specific_campaign":
        if not campaign_id:
            raise BusinessLogicError(code="VALIDATION_ERROR", message="campaign_id обязателен для specific_campaign")
        result = await session.execute(select(Campaign).where(Campaign.id == campaign_id, Campaign.status == CampaignStatus.active))
        if result.scalar_one_or_none() is None:
            raise BusinessLogicError(code="CAMPAIGN_NOT_ACTIVE", message="Кампания не активна")
    elif strategy == "foundation_pool":
        if not foundation_id:
            raise BusinessLogicError(code="VALIDATION_ERROR", message="foundation_id обязателен для foundation_pool")

    sub = Subscription(
        id=uuid7(),
        user_id=user_id,
        amount_kopecks=amount,
        billing_period=data["billing_period"],
        allocation_strategy=data["allocation_strategy"],
        campaign_id=campaign_id if strategy == "specific_campaign" else None,
        foundation_id=foundation_id if strategy == "foundation_pool" else None,
        status=SubscriptionStatus.pending_payment_method,
    )
    session.add(sub)
    await session.flush()
    return sub


async def list_subscriptions(session: AsyncSession, user_id: UUID) -> list[Subscription]:
    result = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.is_deleted == False,
            Subscription.status.in_(["active", "paused", "pending_payment_method"]),
        )
        .order_by(Subscription.created_at.desc())
    )
    return list(result.scalars().all())


async def get_subscription(session: AsyncSession, sub_id: UUID, user_id: UUID) -> Subscription:
    result = await session.execute(
        select(Subscription).where(Subscription.id == sub_id, Subscription.user_id == user_id, Subscription.is_deleted == False)
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise NotFoundError("Подписка не найдена")
    return sub


async def update_subscription(session: AsyncSession, sub_id: UUID, user_id: UUID, data: dict) -> Subscription:
    sub = await get_subscription(session, sub_id, user_id)
    if data.get("amount_kopecks"):
        try:
            validate_subscription_amount(data["amount_kopecks"])
        except InvalidSubscriptionAmount:
            raise BusinessLogicError(code="INVALID_AMOUNT", message=f"Допустимые суммы: {sorted(ALLOWED_SUBSCRIPTION_AMOUNTS)}")

    for key, value in data.items():
        if value is not None:
            setattr(sub, key, value)
    await session.flush()
    return sub


async def pause_subscription(session: AsyncSession, sub_id: UUID, user_id: UUID) -> Subscription:
    sub = await get_subscription(session, sub_id, user_id)
    if sub.status != SubscriptionStatus.active:
        raise BusinessLogicError(code="SUBSCRIPTION_NOT_ACTIVE", message="Подписка не активна")
    sub.status = SubscriptionStatus.paused
    sub.paused_reason = "user_request"
    sub.paused_at = datetime.now(timezone.utc)
    sub.next_billing_at = None
    await session.flush()
    return sub


async def resume_subscription(session: AsyncSession, sub_id: UUID, user_id: UUID) -> Subscription:
    sub = await get_subscription(session, sub_id, user_id)
    if sub.status != SubscriptionStatus.paused:
        raise BusinessLogicError(code="SUBSCRIPTION_NOT_ACTIVE", message="Подписка не на паузе")
    period_days = 7 if sub.billing_period == BillingPeriod.weekly else 30
    sub.status = SubscriptionStatus.active
    sub.paused_reason = None
    sub.paused_at = None
    sub.next_billing_at = datetime.now(timezone.utc) + timedelta(days=period_days)
    await session.flush()
    return sub


async def cancel_subscription(session: AsyncSession, sub_id: UUID, user_id: UUID) -> None:
    sub = await get_subscription(session, sub_id, user_id)
    sub.status = SubscriptionStatus.cancelled
    sub.cancelled_at = datetime.now(timezone.utc)
    sub.next_billing_at = None
    await session.flush()


async def bind_card(session: AsyncSession, sub_id: UUID, user_id: UUID) -> dict:
    """Initiate first payment for card binding."""
    sub = await get_subscription(session, sub_id, user_id)
    if sub.status != SubscriptionStatus.pending_payment_method:
        raise BusinessLogicError(code="SUBSCRIPTION_ALREADY_ACTIVE", message="Карта уже привязана к подписке")

    bp = sub.billing_period.value if hasattr(sub.billing_period, 'value') else sub.billing_period
    amount = billing_amount(sub.amount_kopecks, bp)
    period_label = "еженедельно" if bp == "weekly" else "ежемесячно"
    rub = sub.amount_kopecks / 100

    # TODO: create YooKassa payment with save_payment_method=true
    idempotence_key = str(uuid7())

    # Create Transaction record for the first payment
    fees = calculate_fees(amount)
    txn = Transaction(
        id=uuid7(),
        subscription_id=sub.id,
        campaign_id=sub.campaign_id,
        foundation_id=sub.foundation_id,
        amount_kopecks=amount,
        platform_fee_kopecks=fees["platform_fee_kopecks"],
        nco_amount_kopecks=fees["nco_amount_kopecks"],
        idempotence_key=idempotence_key,
        status=TransactionStatus.pending,
    )
    session.add(txn)
    await session.flush()

    payment_url = f"https://yookassa.ru/pay/{idempotence_key}"

    return {
        "payment_url": payment_url,
        "confirmation_type": "redirect",
        "subscription_id": sub.id,
        "amount_kopecks": amount,
        "description": f"Подписка «По Рублю» — {rub:.0f}₽/день ({period_label})",
    }
