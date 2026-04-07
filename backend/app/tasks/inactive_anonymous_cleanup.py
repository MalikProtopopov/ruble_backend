"""Cleanup task: cancel inactive anonymous accounts.

Anonymous users created via /auth/device-register that go without ANY authenticated
request for `ANONYMOUS_INACTIVE_DAYS` days (default 180 = ~6 months) are considered
abandoned. We:

  1. Cancel their active recurring subscriptions (status → cancelled). The billing
     cron only charges status=active, so no further YooKassa charges happen.
  2. Soft-delete every saved payment method.
  3. Send a "your subscription was cancelled — sign back in to restore" push to
     users that have a push_token, so the user has a chance to recover via the
     account-merge / fingerprint-recovery flow.
  4. Revoke all refresh tokens.
  5. If the user has historical donations or subscriptions → soft-delete the User
     row (preserves donation history for stats; payment methods are CASCADE-deleted
     by FK only on hard delete, so we explicitly mark them deleted in step 2).
     Otherwise → hard-delete the User row (CASCADE wipes payment_methods +
     refresh_tokens).

Runs once a day. Idempotent: re-running on the same already-cancelled user is a no-op.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func as sa_func, or_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.models import (
    Donation,
    PaymentMethod,
    RefreshToken,
    Subscription,
    User,
)
from app.models.base import SubscriptionStatus
from app.services.notification import send_push
from app.tasks import broker

logger = get_logger(__name__)


# Process at most this many users per cron run. Avoids holding a huge transaction
# if a backlog accumulates after a long downtime — the next run picks up the rest.
CLEANUP_BATCH_SIZE = 500


# Daily at 04:30 UTC, after the refresh-token cleanup task at 03:30.
@broker.task(schedule=[{"cron": "30 4 * * *"}])
async def cleanup_inactive_anonymous_users() -> dict:
    """Find and clean up anonymous users with no activity for N days."""
    async with async_session_factory() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ANONYMOUS_INACTIVE_DAYS)

        # Anonymous, not deleted, AND either:
        #   - last_seen_at is older than cutoff, OR
        #   - last_seen_at is NULL AND created_at is older than cutoff
        #     (defensive: covers users created before the column existed or
        #     anything that bypassed the middleware/device-register).
        candidates_q = (
            select(User)
            .where(
                User.is_anonymous == True,  # noqa: E712
                User.is_deleted == False,  # noqa: E712
                or_(
                    User.last_seen_at < cutoff,
                    sa_func.coalesce(User.last_seen_at, User.created_at) < cutoff,
                ),
            )
            .order_by(sa_func.coalesce(User.last_seen_at, User.created_at).asc())
            .limit(CLEANUP_BATCH_SIZE)
        )
        users = list((await session.execute(candidates_q)).scalars().all())

        cancelled_subs = 0
        deleted_pms = 0
        soft_deleted_users = 0
        hard_deleted_users = 0
        pushed_users = 0

        for user in users:
            stats = await _process_user(session, user)
            cancelled_subs += stats["cancelled_subs"]
            deleted_pms += stats["deleted_pms"]
            if stats["pushed"]:
                pushed_users += 1
            if stats["hard_deleted"]:
                hard_deleted_users += 1
            else:
                soft_deleted_users += 1

        await session.commit()

        logger.info(
            "cleanup_inactive_anonymous_done",
            inspected=len(users),
            cancelled_subs=cancelled_subs,
            deleted_pms=deleted_pms,
            soft_deleted_users=soft_deleted_users,
            hard_deleted_users=hard_deleted_users,
            pushed_users=pushed_users,
        )

        return {
            "inspected": len(users),
            "cancelled_subs": cancelled_subs,
            "deleted_pms": deleted_pms,
            "soft_deleted_users": soft_deleted_users,
            "hard_deleted_users": hard_deleted_users,
            "pushed_users": pushed_users,
        }


async def _process_user(session: AsyncSession, user: User) -> dict:
    """Cancel subs / clear PMs / push / delete a single user. Internal helper."""
    now = datetime.now(timezone.utc)

    # 1. Cancel active subscriptions.
    cancel_result = await session.execute(
        sa_update(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(
                [SubscriptionStatus.active, SubscriptionStatus.pending_payment_method]
            ),
        )
        .values(status=SubscriptionStatus.cancelled, cancelled_at=now)
    )
    cancelled_subs = cancel_result.rowcount or 0

    # 2. Soft-delete saved payment methods.
    pm_result = await session.execute(
        sa_update(PaymentMethod)
        .where(
            PaymentMethod.user_id == user.id,
            PaymentMethod.is_deleted == False,  # noqa: E712
        )
        .values(is_deleted=True, deleted_at=now, is_default=False)
    )
    deleted_pms = pm_result.rowcount or 0

    # 3. Push notification — only if there was something to lose AND a token.
    pushed = False
    if cancelled_subs > 0 and user.push_token:
        try:
            await send_push(
                session,
                user_id=user.id,
                push_token=user.push_token,
                notification_type="subscription_expired_inactive",
                title="Подписка приостановлена",
                body="Войдите в приложение, чтобы восстановить подписку и сохранённые карты.",
                data={"type": "subscription_expired_inactive"},
            )
            pushed = True
        except Exception as exc:  # pragma: no cover — push failures must not break cleanup
            logger.warning(
                "cleanup_push_failed", user_id=str(user.id), error=str(exc)
            )

    # 4. Revoke refresh tokens.
    await session.execute(
        sa_update(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
        .values(is_revoked=True)
    )

    # 5. Decide soft- vs hard-delete.
    has_donations = (
        await session.scalar(
            select(sa_func.count(Donation.id)).where(Donation.user_id == user.id)
        )
        or 0
    ) > 0
    has_any_sub = (
        await session.scalar(
            select(sa_func.count(Subscription.id)).where(Subscription.user_id == user.id)
        )
        or 0
    ) > 0

    if has_donations or has_any_sub:
        # Preserve donation/subscription history.
        # FK on subscriptions has ondelete=RESTRICT, so hard delete is impossible
        # anyway when the user has any subscription. Soft-delete frees the
        # device_id slot so the same physical device can register again.
        user.is_deleted = True
        user.deleted_at = now
        user.is_active = False
        user.device_id = None
        await session.flush()
        return {
            "cancelled_subs": cancelled_subs,
            "deleted_pms": deleted_pms,
            "pushed": pushed,
            "hard_deleted": False,
        }

    # No donations, no subscriptions ever — hard-delete. CASCADE on payment_methods
    # and refresh_tokens cleans up the rest.
    await session.execute(delete(User).where(User.id == user.id))
    return {
        "cancelled_subs": cancelled_subs,
        "deleted_pms": deleted_pms,
        "pushed": pushed,
        "hard_deleted": True,
    }
