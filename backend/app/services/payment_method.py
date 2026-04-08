"""Saved payment method service."""

import hashlib
from uuid import UUID

from sqlalchemy import func as sa_func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.core.logging import get_logger
from app.models import Donation, PaymentMethod, Subscription, User
from app.models.base import SubscriptionStatus, uuid7

logger = get_logger(__name__)


def build_card_fingerprint(
    *,
    first6: str | None,
    last4: str | None,
    exp_month: str | None,
    exp_year: str | None,
) -> str | None:
    """Build a deterministic SHA-256 fingerprint for a card.

    Same physical card always produces the same fingerprint, even when YooKassa
    issues a different `payment_method.id` (e.g. after the user re-saves the card
    on a fresh anonymous account). Used by the recovery endpoint to find orphaned
    accounts that hold the same card.

    Returns None if any required component is missing.
    """
    if not last4:
        return None
    parts = [
        (first6 or "").strip(),
        last4.strip(),
        (exp_month or "").strip(),
        (exp_year or "").strip(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
    card_first6: str | None = None,
    card_exp_month: str | None = None,
    card_exp_year: str | None = None,
) -> PaymentMethod:
    """Persist a YooKassa-saved payment method after a successful donation.

    Idempotent: if the same provider_pm_id already exists, returns it.
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

    fingerprint = build_card_fingerprint(
        first6=card_first6,
        last4=card_last4,
        exp_month=card_exp_month,
        exp_year=card_exp_year,
    )

    pm = PaymentMethod(
        id=uuid7(),
        user_id=user_id,
        provider="yookassa",
        provider_pm_id=provider_pm_id,
        card_last4=card_last4,
        card_type=card_type,
        title=title,
        is_default=is_first,
        card_fingerprint=fingerprint,
    )
    session.add(pm)
    await session.flush()
    logger.info(
        "payment_method_saved",
        user_id=str(user_id),
        pm_id=str(pm.id),
        has_fingerprint=fingerprint is not None,
    )
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


async def _user_fingerprints(session: AsyncSession, user_id: UUID) -> list[str]:
    """Return all distinct card fingerprints currently saved for `user_id`."""
    rows = (
        await session.execute(
            select(PaymentMethod.card_fingerprint)
            .where(
                PaymentMethod.user_id == user_id,
                PaymentMethod.is_deleted == False,  # noqa: E712
                PaymentMethod.card_fingerprint.isnot(None),
            )
            .distinct()
        )
    ).scalars().all()
    return [r for r in rows if r]


async def _find_orphans_by_fingerprints(
    session: AsyncSession, *, fingerprints: list[str], current_user_id: UUID
) -> list[dict]:
    if not fingerprints:
        return []
    candidates_q = (
        select(User)
        .join(PaymentMethod, PaymentMethod.user_id == User.id)
        .where(
            PaymentMethod.card_fingerprint.in_(fingerprints),
            PaymentMethod.is_deleted == False,  # noqa: E712
            User.id != current_user_id,
            User.is_anonymous == True,  # noqa: E712
            User.is_deleted == False,  # noqa: E712
        )
        .distinct()
    )
    candidates = list((await session.execute(candidates_q)).scalars().all())

    out: list[dict] = []
    for cand in candidates:
        donations_count = await session.scalar(
            select(sa_func.count(Donation.id)).where(Donation.user_id == cand.id)
        )
        subscriptions_count = await session.scalar(
            select(sa_func.count(Subscription.id)).where(Subscription.user_id == cand.id)
        )
        active_subs = await session.scalar(
            select(sa_func.count(Subscription.id)).where(
                Subscription.user_id == cand.id,
                Subscription.status == SubscriptionStatus.active,
            )
        )
        out.append(
            {
                "user_id": cand.id,
                "donations_count": int(donations_count or 0),
                "subscriptions_count": int(subscriptions_count or 0),
                "active_subscriptions_count": int(active_subs or 0),
                "total_donated_kopecks": int(cand.total_donated_kopecks or 0),
                "last_seen_at": cand.last_seen_at,
            }
        )
    return out


async def find_orphaned_accounts(
    session: AsyncSession,
    *,
    pm_id: UUID,
    current_user_id: UUID,
) -> list[dict]:
    """Find OTHER anonymous users that hold a payment method with the same
    fingerprint as the given PM. (Per-PM variant — kept for explicit flows.)
    """
    pm = await get_for_user(session, pm_id, current_user_id)
    if not pm.card_fingerprint:
        return []
    return await _find_orphans_by_fingerprints(
        session, fingerprints=[pm.card_fingerprint], current_user_id=current_user_id
    )


async def find_all_orphaned_accounts_for_user(
    session: AsyncSession, *, current_user_id: UUID
) -> list[dict]:
    """Scan ALL non-deleted payment methods of the current user and find orphans
    matching any of their fingerprints.

    Recommended for mobile: call this right after the donation/subscription
    success flow without knowing which specific PM was just saved. The mobile
    app does NOT need to poll for the exact pm_id created in the webhook.
    """
    fingerprints = await _user_fingerprints(session, current_user_id)
    return await _find_orphans_by_fingerprints(
        session, fingerprints=fingerprints, current_user_id=current_user_id
    )


async def _recover_by_fingerprints(
    session: AsyncSession,
    *,
    fingerprints: list[str],
    current_user_id: UUID,
) -> dict:
    """Merge all anonymous orphans matching any of the provided fingerprints
    into the current user. Returns aggregate counters."""
    from app.services.account_merge import merge_anonymous_into  # circular guard

    if not fingerprints:
        return {
            "merged_user_ids": [],
            "donations_transferred": 0,
            "subscriptions_transferred": 0,
            "total_donated_kopecks_transferred": 0,
        }

    cur_result = await session.execute(
        select(User).where(User.id == current_user_id, User.is_deleted == False)  # noqa: E712
    )
    target = cur_result.scalar_one()

    candidates_q = (
        select(User)
        .join(PaymentMethod, PaymentMethod.user_id == User.id)
        .where(
            PaymentMethod.card_fingerprint.in_(fingerprints),
            PaymentMethod.is_deleted == False,  # noqa: E712
            User.id != current_user_id,
            User.is_anonymous == True,  # noqa: E712
            User.is_deleted == False,  # noqa: E712
        )
        .distinct()
    )
    candidates = list((await session.execute(candidates_q)).scalars().all())

    merged_ids: list[UUID] = []
    donations_total = 0
    subscriptions_total = 0
    kopecks_total = 0
    for cand in candidates:
        donations_total += int(
            await session.scalar(
                select(sa_func.count(Donation.id)).where(Donation.user_id == cand.id)
            )
            or 0
        )
        subscriptions_total += int(
            await session.scalar(
                select(sa_func.count(Subscription.id)).where(Subscription.user_id == cand.id)
            )
            or 0
        )
        kopecks_total += int(cand.total_donated_kopecks or 0)
        await merge_anonymous_into(session, source=cand, target=target)
        merged_ids.append(cand.id)

    logger.info(
        "orphaned_accounts_recovered",
        target_user_id=str(current_user_id),
        merged_count=len(merged_ids),
    )
    return {
        "merged_user_ids": merged_ids,
        "donations_transferred": donations_total,
        "subscriptions_transferred": subscriptions_total,
        "total_donated_kopecks_transferred": kopecks_total,
    }


async def recover_orphaned_accounts(
    session: AsyncSession,
    *,
    pm_id: UUID,
    current_user_id: UUID,
) -> dict:
    """Per-PM recovery (explicit). See `recover_all_orphaned_accounts_for_user`
    for the simpler "scan everything" variant the mobile flow should use.
    """
    pm = await get_for_user(session, pm_id, current_user_id)
    if not pm.card_fingerprint:
        raise BusinessLogicError(
            code="PM_NO_FINGERPRINT",
            message="Этот способ оплаты не поддерживает восстановление аккаунта.",
        )
    return await _recover_by_fingerprints(
        session,
        fingerprints=[pm.card_fingerprint],
        current_user_id=current_user_id,
    )


async def recover_all_orphaned_accounts_for_user(
    session: AsyncSession, *, current_user_id: UUID
) -> dict:
    """Scan-and-merge variant: takes ALL fingerprints saved on the current user
    and merges every matching orphan in one shot.

    Recommended endpoint for the mobile flow — no need to know a specific pm_id.
    """
    fingerprints = await _user_fingerprints(session, current_user_id)
    return await _recover_by_fingerprints(
        session, fingerprints=fingerprints, current_user_id=current_user_id
    )


# ---------------------------------------------------------------------------
# Maintenance helpers (admin / one-shot)
# ---------------------------------------------------------------------------


async def backfill_fingerprints_from_yookassa(session: AsyncSession) -> dict:
    """For every PaymentMethod with NULL fingerprint, fetch the original payment
    from YooKassa to extract first6/last4/expiry and compute the fingerprint.

    `provider_pm_id` for cards saved via the first donation equals the YooKassa
    payment.id of that donation, so `get_payment(provider_pm_id)` returns the
    payment object that contains the saved `payment_method.card` data.

    Best-effort: a YooKassa API failure for one PM is logged and skipped.
    """
    from app.services.yookassa import yookassa_client

    rows = (
        await session.execute(
            select(PaymentMethod).where(
                PaymentMethod.is_deleted == False,  # noqa: E712
                PaymentMethod.card_fingerprint.is_(None),
                PaymentMethod.provider == "yookassa",
            )
        )
    ).scalars().all()

    filled = 0
    failed: list[dict] = []
    for pm in rows:
        try:
            payment = await yookassa_client.get_payment(pm.provider_pm_id)
        except Exception as exc:
            failed.append({"pm_id": str(pm.id), "error": type(exc).__name__})
            logger.warning(
                "fingerprint_backfill_yookassa_error",
                pm_id=str(pm.id),
                provider_pm_id=pm.provider_pm_id,
                error=type(exc).__name__,
            )
            continue

        card = (payment.get("payment_method") or {}).get("card") or {}
        fp = build_card_fingerprint(
            first6=card.get("first6"),
            last4=card.get("last4"),
            exp_month=card.get("expiry_month"),
            exp_year=card.get("expiry_year"),
        )
        if fp is None:
            failed.append({"pm_id": str(pm.id), "error": "no_card_data"})
            logger.warning(
                "fingerprint_backfill_no_card_data",
                pm_id=str(pm.id),
                provider_pm_id=pm.provider_pm_id,
            )
            continue

        pm.card_fingerprint = fp
        # Also backfill last4/type if missing.
        if not pm.card_last4 and card.get("last4"):
            pm.card_last4 = card["last4"]
        if not pm.card_type and card.get("card_type"):
            pm.card_type = card["card_type"]
        filled += 1

    await session.flush()
    logger.info(
        "fingerprint_backfill_done",
        scanned=len(rows),
        filled=filled,
        failed=len(failed),
    )
    return {
        "scanned": len(rows),
        "filled": filled,
        "failed": len(failed),
        "failed_items": failed,
    }


async def dedupe_payment_methods(session: AsyncSession) -> dict:
    """Soft-delete duplicate payment methods per user.

    Two PMs are considered duplicates if they share `card_fingerprint`. The
    NEWEST one is kept (most recently saved → most likely the one the user
    expects to be the active card). Older duplicates are soft-deleted. After
    pruning we ensure exactly one PM per user is `is_default=true`.

    Idempotent — running twice on a clean state is a no-op.
    """
    # Pull all non-deleted PMs with non-null fingerprint, grouped per user.
    pms = (
        await session.execute(
            select(PaymentMethod)
            .where(
                PaymentMethod.is_deleted == False,  # noqa: E712
                PaymentMethod.card_fingerprint.isnot(None),
            )
            .order_by(PaymentMethod.user_id, PaymentMethod.created_at.desc())
        )
    ).scalars().all()

    # Bucket per (user_id, fingerprint).
    from collections import defaultdict
    from datetime import datetime, timezone

    buckets: dict[tuple, list[PaymentMethod]] = defaultdict(list)
    for pm in pms:
        buckets[(pm.user_id, pm.card_fingerprint)].append(pm)

    soft_deleted = 0
    affected_users: set = set()
    now = datetime.now(timezone.utc)
    for (user_id, _fp), group in buckets.items():
        if len(group) <= 1:
            continue
        # group is already ordered by created_at DESC; keep [0], drop the rest.
        keep = group[0]
        for dup in group[1:]:
            dup.is_deleted = True
            dup.deleted_at = now
            dup.is_default = False
            soft_deleted += 1
        # Make sure the kept one carries is_default if the user has nothing
        # else marked default. We'll resolve the per-user default below.
        affected_users.add(user_id)

    # For each affected user: ensure exactly one default PM survives.
    for user_id in affected_users:
        live = (
            await session.execute(
                select(PaymentMethod)
                .where(
                    PaymentMethod.user_id == user_id,
                    PaymentMethod.is_deleted == False,  # noqa: E712
                )
                .order_by(PaymentMethod.created_at.desc())
            )
        ).scalars().all()
        if not live:
            continue
        seen_default = False
        for pm in live:
            if pm.is_default and not seen_default:
                seen_default = True
                continue
            if pm.is_default:
                pm.is_default = False
        if not seen_default:
            live[0].is_default = True

    await session.flush()
    logger.info(
        "payment_methods_deduped",
        soft_deleted=soft_deleted,
        affected_users=len(affected_users),
    )
    return {
        "soft_deleted": soft_deleted,
        "affected_users": len(affected_users),
    }
