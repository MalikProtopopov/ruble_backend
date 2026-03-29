"""Recurring subscription billing — creates transactions and charges saved cards.

Runs every 30 minutes. Finds active subscriptions where next_billing_at <= now()
and creates new transactions + YooKassa payments.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.domain.constants import SOFT_DECLINE_RETRY_DAYS
from app.domain.subscription import billing_amount
from app.models import Subscription, Transaction
from app.models.base import SubscriptionStatus, TransactionStatus, uuid7
from app.services.payment import calculate_fees
from app.services.yookassa import yookassa_client
from app.tasks import broker

logger = get_logger(__name__)


@broker.task(schedule=[{"cron": "*/30 * * * *"}])
async def process_recurring_billing() -> dict:
    """Charge subscriptions that are due for billing."""
    async with async_session_factory() as session:
        now = datetime.now(timezone.utc)

        # Find active subscriptions due for billing
        result = await session.execute(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.active,
                Subscription.next_billing_at <= now,
                Subscription.payment_method_id.isnot(None),
            )
        )
        subscriptions = list(result.scalars().all())

        charged = 0
        failed = 0

        for sub in subscriptions:
            try:
                await _charge_subscription(session, sub)
                charged += 1
            except Exception:
                logger.exception("billing_charge_error", subscription_id=str(sub.id))
                failed += 1

        await session.commit()

        logger.info("recurring_billing_complete", charged=charged, failed=failed, total=len(subscriptions))
        return {"charged": charged, "failed": failed, "total": len(subscriptions)}


@broker.task(schedule=[{"cron": "0 */6 * * *"}])
async def retry_failed_transactions() -> dict:
    """Retry failed transactions that are scheduled for retry."""
    async with async_session_factory() as session:
        now = datetime.now(timezone.utc)

        result = await session.execute(
            select(Transaction).where(
                Transaction.status == TransactionStatus.failed,
                Transaction.next_retry_at <= now,
                Transaction.next_retry_at.isnot(None),
            )
        )
        transactions = list(result.scalars().all())

        retried = 0
        errors = 0

        for txn in transactions:
            try:
                await _retry_transaction(session, txn)
                retried += 1
            except Exception:
                logger.exception("retry_error", transaction_id=str(txn.id))
                errors += 1

        await session.commit()

        logger.info("retry_complete", retried=retried, errors=errors, total=len(transactions))
        return {"retried": retried, "errors": errors}


async def _charge_subscription(session: AsyncSession, sub: Subscription) -> None:
    """Create a new transaction and charge via YooKassa."""
    bp = sub.billing_period.value if hasattr(sub.billing_period, "value") else sub.billing_period
    amount = billing_amount(sub.amount_kopecks, bp)
    fees = calculate_fees(amount)
    idempotence_key = str(uuid7())

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

    rub = sub.amount_kopecks / 100
    period_label = "еженедельно" if bp == "weekly" else "ежемесячно"

    payment = await yookassa_client.create_recurring_payment(
        amount_kopecks=amount,
        description=f"Подписка «По Рублю» — {rub:.0f}₽/день ({period_label})"[:128],
        idempotence_key=idempotence_key,
        payment_method_id=sub.payment_method_id,
        metadata={
            "type": "transaction",
            "entity_id": str(txn.id),
            "subscription_id": str(sub.id),
        },
    )
    txn.provider_payment_id = payment["id"]
    await session.flush()

    logger.info(
        "subscription_charged",
        subscription_id=str(sub.id),
        transaction_id=str(txn.id),
        amount=amount,
    )


async def _retry_transaction(session: AsyncSession, txn: Transaction) -> None:
    """Retry a failed transaction by creating a new YooKassa payment."""
    # Get subscription for payment_method_id
    sub_result = await session.execute(
        select(Subscription).where(Subscription.id == txn.subscription_id)
    )
    sub = sub_result.scalar_one_or_none()
    if not sub or not sub.payment_method_id:
        txn.next_retry_at = None  # Can't retry without payment method
        await session.flush()
        return

    if sub.status != SubscriptionStatus.active:
        txn.next_retry_at = None
        await session.flush()
        return

    # Create new idempotence key for retry
    new_idempotence_key = str(uuid7())
    txn.attempt_number += 1
    txn.status = TransactionStatus.pending
    txn.idempotence_key = new_idempotence_key
    txn.next_retry_at = None
    txn.cancellation_reason = None

    rub = sub.amount_kopecks / 100
    bp = sub.billing_period.value if hasattr(sub.billing_period, "value") else sub.billing_period
    period_label = "еженедельно" if bp == "weekly" else "ежемесячно"

    payment = await yookassa_client.create_recurring_payment(
        amount_kopecks=txn.amount_kopecks,
        description=f"Подписка «По Рублю» — {rub:.0f}₽/день ({period_label}), попытка {txn.attempt_number}"[:128],
        idempotence_key=new_idempotence_key,
        payment_method_id=sub.payment_method_id,
        metadata={
            "type": "transaction",
            "entity_id": str(txn.id),
            "subscription_id": str(sub.id),
        },
    )
    txn.provider_payment_id = payment["id"]
    await session.flush()

    logger.info(
        "transaction_retried",
        transaction_id=str(txn.id),
        attempt=txn.attempt_number,
    )
