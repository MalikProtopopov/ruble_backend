"""Account merge — anonymous (source) → existing (target).

Used when a guest user provides an email that already belongs to another account.
All transfers happen in a single transaction; the caller is responsible for the
session lifetime / commit.
"""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessLogicError
from app.core.logging import get_logger
from app.models import (
    Donation,
    NotificationLog,
    RefreshToken,
    Subscription,
    User,
)
from app.models.base import SubscriptionStatus

logger = get_logger(__name__)


async def merge_anonymous_into(
    session: AsyncSession,
    *,
    source: User,
    target: User,
) -> User:
    """Merge `source` (anonymous) into `target` (regular). Soft-deletes source.

    Idempotent: if source is already non-anonymous or already deleted, no-op.
    """
    if source.id == target.id:
        return target
    if source.is_deleted:
        return target
    if not source.is_anonymous:
        raise BusinessLogicError(
            code="MERGE_NOT_ALLOWED",
            message="Сливать можно только гостевые аккаунты.",
        )

    src_id = source.id
    tgt_id = target.id

    # 1. Donations
    await session.execute(
        update(Donation).where(Donation.user_id == src_id).values(user_id=tgt_id)
    )

    # 2. Subscriptions — Transaction.user_id doesn't exist; it links via Subscription.
    await session.execute(
        update(Subscription).where(Subscription.user_id == src_id).values(user_id=tgt_id)
    )

    # 3. Notification logs
    await session.execute(
        update(NotificationLog)
        .where(NotificationLog.user_id == src_id)
        .values(user_id=tgt_id)
    )

    # 4. Payment methods (model added in a separate migration; import lazily).
    try:
        from app.models.payment_method import PaymentMethod  # noqa: WPS433

        await session.execute(
            update(PaymentMethod)
            .where(PaymentMethod.user_id == src_id)
            .values(user_id=tgt_id)
        )

        # Dedupe is_default: at most one PM per user can be default. Keep the
        # newest non-deleted one as default, demote the rest.
        all_pms = (await session.execute(
            select(PaymentMethod)
            .where(
                PaymentMethod.user_id == tgt_id,
                PaymentMethod.is_deleted == False,  # noqa: E712
            )
            .order_by(PaymentMethod.created_at.desc())
        )).scalars().all()
        seen_default = False
        for pm in all_pms:
            if pm.is_default and not seen_default:
                seen_default = True
                continue
            if pm.is_default:
                pm.is_default = False
        # If nothing was marked default, promote the newest one.
        if all_pms and not seen_default:
            all_pms[0].is_default = True
    except ImportError:
        pass

    # 4b. Deduplicate active subscriptions on the merged target. After moving
    # source's subs into target, target may have several `active` subscriptions
    # competing for charges (e.g. both source and target had a monthly platform
    # subscription). Keep the OLDEST one (longest streak) and cancel the rest —
    # otherwise the user gets double-billed by the recurring billing job.
    active_subs = (await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == tgt_id,
            Subscription.status == SubscriptionStatus.active,
            Subscription.is_deleted == False,  # noqa: E712
        )
        .order_by(Subscription.created_at.asc())
    )).scalars().all()
    if len(active_subs) > 1:
        for dup in active_subs[1:]:
            dup.status = SubscriptionStatus.cancelled
            dup.cancelled_at = datetime.now(timezone.utc)
        logger.info(
            "merge_dedup_subscriptions",
            target_user_id=str(tgt_id),
            cancelled_count=len(active_subs) - 1,
        )

    # 5. Revoke source refresh tokens
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == src_id, RefreshToken.is_revoked == False)  # noqa: E712
        .values(is_revoked=True)
    )

    # 6. Aggregate counters
    target.total_donated_kopecks = (target.total_donated_kopecks or 0) + (
        source.total_donated_kopecks or 0
    )
    target.total_donations_count = (target.total_donations_count or 0) + (
        source.total_donations_count or 0
    )

    # Streak: keep the higher value, more recent date.
    if (source.current_streak_days or 0) > (target.current_streak_days or 0):
        target.current_streak_days = source.current_streak_days
    if source.last_streak_date and (
        target.last_streak_date is None or source.last_streak_date > target.last_streak_date
    ):
        target.last_streak_date = source.last_streak_date

    # Push token: backfill if target had none.
    if not target.push_token and source.push_token:
        target.push_token = source.push_token
        target.push_platform = source.push_platform

    # 7. Soft-delete source
    source.is_deleted = True
    source.deleted_at = datetime.now(timezone.utc)
    source.is_active = False
    source.device_id = None  # free up the device_id slot

    await session.flush()

    logger.info(
        "account_merged",
        source_user_id=str(src_id),
        target_user_id=str(tgt_id),
    )
    return target
