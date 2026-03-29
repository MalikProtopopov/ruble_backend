"""YooKassa webhook handler."""

from uuid import UUID

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Donation, PatronPaymentLink, Subscription, Transaction, User
from app.models.base import DonationStatus, PatronLinkStatus, SubscriptionStatus, TransactionStatus
from app.services.yookassa import yookassa_client
from app.services.impact import check_and_award_achievements
from app.services.notification import send_push
from app.services.payment import process_successful_payment
from app.domain.constants import SOFT_DECLINE_RETRY_DAYS
from app.services.thanks import find_unseen_thanks_for_campaign
from datetime import datetime, timedelta, timezone

logger = get_logger(__name__)


async def process_yookassa_webhook(session: AsyncSession, event: dict) -> dict:
    """Dispatch YooKassa webhook event to appropriate handler."""
    event_type = event.get("event")
    payment_obj = event.get("object", {})
    payment_id = payment_obj.get("id")
    metadata = payment_obj.get("metadata", {})

    if event_type == "payment.succeeded":
        await handle_payment_succeeded(session, payment_id, metadata, payment_obj)
        return {"status": "ok", "event": event_type}
    elif event_type == "payment.canceled":
        reason = payment_obj.get("cancellation_details", {}).get("reason")
        await handle_payment_canceled(session, payment_id, reason)
        return {"status": "ok", "event": event_type}
    else:
        logger.warning("yookassa_unknown_event", event_type=event_type)
        return {"status": "ignored", "event": event_type}


async def handle_payment_succeeded(
    session: AsyncSession, payment_id: str, metadata: dict, payment_obj: dict | None = None,
) -> None:
    """Handle payment.succeeded webhook from YooKassa."""
    payment_type = metadata.get("type")  # donation, transaction, patron_link
    entity_id = metadata.get("entity_id")

    if payment_type == "donation":
        result = await session.execute(select(Donation).where(Donation.provider_payment_id == payment_id))
        donation = result.scalar_one_or_none()
        if donation and donation.status == DonationStatus.pending:
            donation.status = DonationStatus.success
            await session.flush()
            await process_successful_payment(session, donation.campaign_id, donation.user_id, donation.amount_kopecks)
            # Check for thanks content and achievements
            if donation.user_id:
                thanks_id = await find_unseen_thanks_for_campaign(session, donation.user_id, donation.campaign_id)
                if thanks_id:
                    logger.info("thanks_available", donation_id=str(donation.id), thanks_id=str(thanks_id))
                await check_and_award_achievements(session, donation.user_id)
                # NOTIF-01: Push notification for successful donation
                user_result = await session.execute(select(User).where(User.id == donation.user_id))
                user = user_result.scalar_one_or_none()
                if user and user.push_token and user.notification_preferences.get("push_on_payment", True):
                    rub = donation.amount_kopecks / 100
                    await send_push(
                        session, user_id=user.id, push_token=user.push_token,
                        notification_type="donation_success",
                        title=f"Пожертвование {rub:.0f}\u20bd",
                        body="Спасибо за поддержку!",
                        data={"type": "donation_success", "donation_id": str(donation.id)},
                    )
            logger.info("donation_succeeded", donation_id=str(donation.id))

    elif payment_type == "transaction":
        result = await session.execute(select(Transaction).where(Transaction.provider_payment_id == payment_id))
        txn = result.scalar_one_or_none()
        if txn and txn.status == TransactionStatus.pending:
            txn.status = TransactionStatus.success

            # Get subscription to access user_id and billing period
            sub_result = await session.execute(select(Subscription).where(Subscription.id == txn.subscription_id))
            sub = sub_result.scalar_one_or_none()

            await session.flush()
            if txn.campaign_id:
                user_id = sub.user_id if sub else None
                await process_successful_payment(session, txn.campaign_id, user_id, txn.amount_kopecks)

            # Activate subscription and save payment method if this is the first payment
            if sub:
                days = 7 if sub.billing_period.value == "weekly" else 30
                sub.next_billing_at = datetime.now(timezone.utc) + timedelta(days=days)

                if sub.status == SubscriptionStatus.pending_payment_method:
                    sub.status = SubscriptionStatus.active
                    # Extract saved payment_method_id from webhook payload or API
                    pm = (payment_obj or {}).get("payment_method", {})
                    if pm.get("saved") and pm.get("id"):
                        sub.payment_method_id = pm["id"]
                        logger.info("payment_method_saved", subscription_id=str(sub.id), pm_id=pm["id"])
                    elif not sub.payment_method_id:
                        # Fallback: fetch payment details from API to get payment_method
                        try:
                            full_payment = await yookassa_client.get_payment(payment_id)
                            pm_data = full_payment.get("payment_method", {})
                            if pm_data.get("saved") and pm_data.get("id"):
                                sub.payment_method_id = pm_data["id"]
                                logger.info("payment_method_saved_via_api", subscription_id=str(sub.id))
                        except Exception:
                            logger.warning("failed_to_fetch_payment_method", payment_id=payment_id)

                await session.flush()

            # Check thanks content and achievements for subscription user
            if sub and sub.user_id and txn.campaign_id:
                thanks_id = await find_unseen_thanks_for_campaign(session, sub.user_id, txn.campaign_id)
                if thanks_id:
                    logger.info("thanks_available", transaction_id=str(txn.id), thanks_id=str(thanks_id))
                await check_and_award_achievements(session, sub.user_id)
            # NOTIF-01: Push notification for successful subscription payment
            if sub and sub.user_id:
                user_result2 = await session.execute(select(User).where(User.id == sub.user_id))
                user = user_result2.scalar_one_or_none()
                if user and user.push_token and user.notification_preferences.get("push_on_payment", True):
                    rub = txn.amount_kopecks / 100
                    await send_push(
                        session, user_id=user.id, push_token=user.push_token,
                        notification_type="payment_success",
                        title=f"Списание {rub:.0f}\u20bd",
                        body=f"Стрик: {user.current_streak_days} дн.",
                        data={"type": "payment_success", "transaction_id": str(txn.id)},
                    )
            logger.info("transaction_succeeded", transaction_id=str(txn.id))

    elif payment_type == "patron_link":
        # Find donation by provider_payment_id
        don_result = await session.execute(select(Donation).where(Donation.provider_payment_id == payment_id))
        donation = don_result.scalar_one_or_none()
        if donation and donation.status == DonationStatus.pending:
            donation.status = DonationStatus.success
            await session.flush()
            await process_successful_payment(session, donation.campaign_id, donation.user_id, donation.amount_kopecks)

            # Update patron link status
            link_result = await session.execute(
                select(PatronPaymentLink).where(PatronPaymentLink.donation_id == donation.id)
            )
            link = link_result.scalar_one_or_none()
            if link:
                link.status = PatronLinkStatus.paid
                await session.flush()

            # Check thanks/achievements
            if donation.user_id:
                await check_and_award_achievements(session, donation.user_id)
            logger.info("patron_link_paid", donation_id=str(donation.id))


async def handle_payment_canceled(session: AsyncSession, payment_id: str, reason: str | None) -> None:
    """Handle payment.canceled webhook."""
    # Check transactions first
    result = await session.execute(select(Transaction).where(Transaction.provider_payment_id == payment_id))
    txn = result.scalar_one_or_none()
    if txn:
        txn.status = TransactionStatus.failed
        txn.cancellation_reason = reason
        # Retry logic: soft decline schedule
        if txn.attempt_number < len(SOFT_DECLINE_RETRY_DAYS):
            delay = SOFT_DECLINE_RETRY_DAYS[min(txn.attempt_number - 1, len(SOFT_DECLINE_RETRY_DAYS) - 1)]
            txn.next_retry_at = datetime.now(timezone.utc) + timedelta(days=delay)
        await session.flush()
        logger.info("transaction_failed", transaction_id=str(txn.id), reason=reason)
        return

    # Check donations
    don_result = await session.execute(select(Donation).where(Donation.provider_payment_id == payment_id))
    donation = don_result.scalar_one_or_none()
    if donation:
        donation.status = DonationStatus.failed
        await session.flush()
        logger.info("donation_failed", donation_id=str(donation.id), reason=reason)
