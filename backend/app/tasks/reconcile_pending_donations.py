"""Reconcile pending donations against YooKassa.

Background: a YooKassa payment can succeed without us ever receiving the
`payment.succeeded` webhook (network glitch, retry exhaustion, IP filter, test
panel quirk). When that happens our `donations.status` stays `pending` forever
even though the user actually paid — and the saved card / subscription don't
get linked.

This task closes the gap by polling YooKassa directly for any donation that
has been `pending` for more than `RECONCILE_MIN_AGE_MINUTES` minutes and
applying the same handler we use for webhooks.

Runs every 5 minutes via taskiq cron. Idempotent — re-running on a donation
already marked success/failed is a no-op.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models import Donation
from app.models.base import DonationStatus
from app.services.yookassa import yookassa_client
from app.tasks import broker

logger = get_logger(__name__)


# Don't reconcile a donation that's just a few seconds old — give the regular
# webhook a chance first. 5 minutes is plenty.
RECONCILE_MIN_AGE_MINUTES = 5

# Cap the per-run batch so a backlog after downtime doesn't tie up the worker.
RECONCILE_BATCH_SIZE = 100

# Stop chasing donations that are extremely stale (user clearly abandoned the
# YooKassa page) — mark them as failed locally so the cooldown unblocks.
RECONCILE_MAX_AGE_HOURS = 24


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def reconcile_pending_donations() -> dict:
    async with async_session_factory() as session:
        now = datetime.now(timezone.utc)
        min_age_cutoff = now - timedelta(minutes=RECONCILE_MIN_AGE_MINUTES)
        max_age_cutoff = now - timedelta(hours=RECONCILE_MAX_AGE_HOURS)

        candidates = (
            await session.execute(
                select(Donation)
                .where(
                    Donation.status == DonationStatus.pending,
                    Donation.provider_payment_id.isnot(None),
                    Donation.created_at < min_age_cutoff,
                    Donation.is_deleted == False,  # noqa: E712
                )
                .order_by(Donation.created_at.asc())
                .limit(RECONCILE_BATCH_SIZE)
            )
        ).scalars().all()

        succeeded = 0
        failed = 0
        abandoned = 0
        skipped = 0
        errors = 0

        for donation in candidates:
            try:
                result = await _reconcile_one(session, donation, max_age_cutoff)
            except Exception as exc:
                errors += 1
                logger.warning(
                    "reconcile_pending_donation_error",
                    donation_id=str(donation.id),
                    provider_payment_id=donation.provider_payment_id,
                    error=type(exc).__name__,
                    detail=str(exc)[:300],
                )
                continue

            if result == "succeeded":
                succeeded += 1
            elif result == "failed":
                failed += 1
            elif result == "abandoned":
                abandoned += 1
            else:
                skipped += 1

        await session.commit()

        logger.info(
            "reconcile_pending_donations_done",
            inspected=len(candidates),
            succeeded=succeeded,
            failed=failed,
            abandoned=abandoned,
            skipped=skipped,
            errors=errors,
        )
        return {
            "inspected": len(candidates),
            "succeeded": succeeded,
            "failed": failed,
            "abandoned": abandoned,
            "skipped": skipped,
            "errors": errors,
        }


async def _reconcile_one(
    session: AsyncSession, donation: Donation, max_age_cutoff: datetime
) -> str:
    """Reconcile one donation. Returns one of:
    - "succeeded": YooKassa says paid and we ran the success handler
    - "failed": YooKassa says cancelled and we updated locally
    - "abandoned": stale and never paid → marked failed locally
    - "skipped": still pending in YooKassa, leave for next run
    """
    payload = await yookassa_client.get_payment(donation.provider_payment_id)
    yk_status = payload.get("status")

    if yk_status == "succeeded":
        # Reuse the existing webhook handler so we get the same side effects:
        # process_successful_payment, payment-method save, achievements, push.
        from app.services.webhook import handle_payment_succeeded

        metadata = payload.get("metadata") or {}
        await handle_payment_succeeded(
            session,
            payment_id=donation.provider_payment_id,
            metadata=metadata,
            payment_obj=payload,
        )
        logger.info(
            "reconcile_donation_succeeded",
            donation_id=str(donation.id),
            provider_payment_id=donation.provider_payment_id,
        )
        return "succeeded"

    if yk_status == "canceled":
        donation.status = DonationStatus.failed
        await session.flush()
        logger.info(
            "reconcile_donation_canceled",
            donation_id=str(donation.id),
            provider_payment_id=donation.provider_payment_id,
            reason=(payload.get("cancellation_details") or {}).get("reason"),
        )
        return "failed"

    # Still pending in YooKassa. If too old → mark abandoned (frees the cooldown
    # so the user can try again).
    if donation.created_at < max_age_cutoff:
        donation.status = DonationStatus.failed
        await session.flush()
        logger.info(
            "reconcile_donation_abandoned",
            donation_id=str(donation.id),
            provider_payment_id=donation.provider_payment_id,
            age_hours=(datetime.now(timezone.utc) - donation.created_at).total_seconds() / 3600,
        )
        return "abandoned"

    return "skipped"
