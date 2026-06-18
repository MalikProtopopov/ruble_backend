"""Refund service — admin-initiated full refunds via YooKassa."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.core.logging import get_logger
from app.models import Donation
from app.models.base import DonationStatus, uuid7
from app.services.payment import reverse_successful_payment
from app.services.yookassa import yookassa_client

logger = get_logger(__name__)


async def refund_donation(session: AsyncSession, donation_id: UUID) -> dict:
    """Initiate a full refund for a successful donation.

    The YooKassa refund is created synchronously; if it returns 'succeeded'
    we flip the donation to `refunded` and reverse its counter effects right
    away. The `refund.succeeded` webhook is idempotent and a safe backstop if
    the synchronous call did not confirm immediately.
    """
    result = await session.execute(
        select(Donation).where(Donation.id == donation_id, Donation.is_deleted == False)  # noqa: E712
    )
    donation = result.scalar_one_or_none()
    if donation is None:
        raise NotFoundError("Пожертвование не найдено")
    if donation.status != DonationStatus.success:
        raise BusinessLogicError(
            code="REFUND_NOT_ALLOWED",
            message="Возврат возможен только для успешного платежа",
        )
    if not donation.provider_payment_id:
        raise BusinessLogicError(
            code="REFUND_NO_PAYMENT",
            message="У пожертвования нет платежа для возврата",
        )

    refund = await yookassa_client.create_refund(
        payment_id=donation.provider_payment_id,
        amount_kopecks=donation.amount_kopecks,
        idempotence_key=str(uuid7()),
        description="Возврат пожертвования",
    )

    if refund.get("status") == "succeeded":
        donation.status = DonationStatus.refunded
        await session.flush()
        await reverse_successful_payment(
            session, donation.campaign_id, donation.user_id, donation.amount_kopecks
        )
        logger.info("donation_refunded_admin", donation_id=str(donation.id), refund_id=refund.get("id"))

    return {
        "donation_id": str(donation.id),
        "refund_id": refund.get("id"),
        "refund_status": refund.get("status"),
        "donation_status": donation.status.value,
    }
