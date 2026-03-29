"""Payment service — atomic counter updates, campaign_donors, streak, fees.

Implements §1.2, §3.2a, §5 of database_requirements.md.
"""

import datetime as dt
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.payment import calculate_fees as _domain_calculate_fees, FeeBreakdown

logger = get_logger(__name__)


def calculate_fees(amount_kopecks: int, acquiring_fee_kopecks: int = 0) -> dict:
    """Calculate platform fee and NCO amount. §5 rule 4.

    Delegates to domain layer; returns dict for backward compatibility.
    """
    fb = _domain_calculate_fees(amount_kopecks, acquiring_fee_kopecks)
    return {"platform_fee_kopecks": fb.platform_fee_kopecks, "nco_amount_kopecks": fb.nco_amount_kopecks}


async def increment_campaign_counters(
    session: AsyncSession,
    campaign_id: UUID,
    amount_kopecks: int,
    user_id: UUID | None,
) -> bool:
    """Atomically update collected_amount and conditionally donors_count.

    §3.2a: INSERT INTO campaign_donors ON CONFLICT DO NOTHING.
    If inserted (new donor) → increment donors_count.
    collected_amount always incremented atomically.

    Returns True if this was a new donor.
    """
    is_new_donor = False

    # Atomic collected_amount increment — §1.2 / §5 rule 5
    await session.execute(
        text("""
            UPDATE campaigns
            SET collected_amount = collected_amount + :amount,
                updated_at = now()
            WHERE id = :campaign_id
        """),
        {"amount": amount_kopecks, "campaign_id": campaign_id},
    )

    # campaign_donors — §3.2a / §5 rule 16
    if user_id is not None:
        result = await session.execute(
            text("""
                INSERT INTO campaign_donors (campaign_id, user_id)
                VALUES (:campaign_id, :user_id)
                ON CONFLICT DO NOTHING
            """),
            {"campaign_id": campaign_id, "user_id": user_id},
        )
        if result.rowcount == 1:
            is_new_donor = True
            await session.execute(
                text("""
                    UPDATE campaigns
                    SET donors_count = donors_count + 1
                    WHERE id = :campaign_id
                """),
                {"campaign_id": campaign_id},
            )

    logger.info(
        "campaign_counters_updated",
        campaign_id=str(campaign_id),
        amount=amount_kopecks,
        new_donor=is_new_donor,
    )
    return is_new_donor


async def check_campaign_auto_complete(session: AsyncSession, campaign_id: UUID) -> bool:
    """Auto-complete campaign if goal reached and not permanent. §3.2 business rules."""
    result = await session.execute(
        text("""
            UPDATE campaigns
            SET status = 'completed', updated_at = now()
            WHERE id = :campaign_id
              AND is_permanent = false
              AND goal_amount IS NOT NULL
              AND collected_amount >= goal_amount
              AND status = 'active'
            RETURNING id
        """),
        {"campaign_id": campaign_id},
    )
    completed = result.fetchone() is not None
    if completed:
        logger.info("campaign_auto_completed", campaign_id=str(campaign_id))
    return completed


async def update_user_streak(session: AsyncSession, user_id: UUID) -> None:
    """Update streak cache in users table. §5 rule 17.

    - last_streak_date = today → no-op
    - last_streak_date = yesterday → streak += 1
    - else → streak = 1
    """
    today = dt.date.today()
    await session.execute(
        text("""
            UPDATE users
            SET current_streak_days = CASE
                    WHEN last_streak_date = :today THEN current_streak_days
                    WHEN last_streak_date = :yesterday THEN current_streak_days + 1
                    ELSE 1
                END,
                last_streak_date = :today,
                updated_at = now()
            WHERE id = :user_id
        """),
        {
            "user_id": user_id,
            "today": today,
            "yesterday": today - dt.timedelta(days=1),
        },
    )


async def update_user_impact(
    session: AsyncSession,
    user_id: UUID,
    amount_kopecks: int,
) -> None:
    """Atomically increment user impact counters. §5 rule 21."""
    await session.execute(
        text("""
            UPDATE users
            SET total_donated_kopecks = total_donated_kopecks + :amount,
                total_donations_count = total_donations_count + 1,
                updated_at = now()
            WHERE id = :user_id
        """),
        {"user_id": user_id, "amount": amount_kopecks},
    )


async def mark_streak_no_campaigns(session: AsyncSession, user_id: UUID) -> None:
    """ALLOC-05 / §5 rule 17: skipped due to no_active_campaigns — don't break streak."""
    today = dt.date.today()
    await session.execute(
        text("""
            UPDATE users
            SET last_streak_date = :today,
                updated_at = now()
            WHERE id = :user_id
              AND (last_streak_date IS NULL OR last_streak_date < :today)
        """),
        {"user_id": user_id, "today": today},
    )


async def process_successful_payment(
    session: AsyncSession,
    campaign_id: UUID,
    user_id: UUID | None,
    amount_kopecks: int,
) -> None:
    """Full flow after a successful payment (transaction or donation).

    1. Increment campaign counters + campaign_donors
    2. Check auto-complete
    3. Update user streak
    4. Update user impact
    """
    await increment_campaign_counters(session, campaign_id, amount_kopecks, user_id)
    await check_campaign_auto_complete(session, campaign_id)

    if user_id is not None:
        await update_user_streak(session, user_id)
        await update_user_impact(session, user_id, amount_kopecks)
