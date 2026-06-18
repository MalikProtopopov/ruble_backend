"""§8 — Daily reconciliation tasks.

Compares denormalized counters with real data, logs every discrepancy AND
auto-corrects the cached counter to match the source of truth (sum/count over
the authoritative rows). Each task returns the number of rows corrected.
"""

from sqlalchemy import text

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.tasks import broker

logger = get_logger(__name__)


@broker.task(schedule=[{"cron": "0 5 * * *"}])
async def reconcile_collected_amount() -> int:
    """Reconcile campaigns.collected_amount with SUM of success transactions + donations + offline."""
    real_expr = """(
        COALESCE((SELECT SUM(amount_kopecks) FROM transactions WHERE campaign_id = c.id AND status = 'success'), 0)
      + COALESCE((SELECT SUM(amount_kopecks) FROM donations WHERE campaign_id = c.id AND status = 'success'), 0)
      + COALESCE((SELECT SUM(amount_kopecks) FROM offline_payments WHERE campaign_id = c.id), 0)
    )"""
    async with async_session_factory() as session:
        rows = await session.execute(text(f"""
            SELECT c.id, c.collected_amount, {real_expr} AS real_amount
            FROM campaigns c
            WHERE c.collected_amount != {real_expr}
        """))
        discrepancies = rows.fetchall()
        for campaign_id, cached, real in discrepancies:
            logger.warning(
                "reconcile_collected_amount_corrected",
                campaign_id=str(campaign_id), cached=cached, real=real, diff=cached - real,
            )
        if discrepancies:
            await session.execute(text(f"""
                UPDATE campaigns c
                SET collected_amount = {real_expr}, updated_at = now()
                WHERE c.collected_amount != {real_expr}
            """))
            await session.commit()
        logger.info("reconcile_collected_amount_done", corrected=len(discrepancies))
        return len(discrepancies)


@broker.task(schedule=[{"cron": "5 5 * * *"}])
async def reconcile_donors_count() -> int:
    """Reconcile campaigns.donors_count with COUNT from campaign_donors."""
    real_expr = "(SELECT COUNT(*) FROM campaign_donors cd WHERE cd.campaign_id = c.id)"
    async with async_session_factory() as session:
        rows = await session.execute(text(f"""
            SELECT c.id, c.donors_count, {real_expr} AS real_count
            FROM campaigns c
            WHERE c.donors_count != {real_expr}
        """))
        discrepancies = rows.fetchall()
        for campaign_id, cached, real in discrepancies:
            logger.warning(
                "reconcile_donors_count_corrected",
                campaign_id=str(campaign_id), cached=cached, real=real,
            )
        if discrepancies:
            await session.execute(text(f"""
                UPDATE campaigns c
                SET donors_count = {real_expr}
                WHERE c.donors_count != {real_expr}
            """))
            await session.commit()
        logger.info("reconcile_donors_count_done", corrected=len(discrepancies))
        return len(discrepancies)


@broker.task(schedule=[{"cron": "10 5 * * *"}])
async def reconcile_user_impact() -> int:
    """Reconcile users.total_donated_kopecks / total_donations_count with real data."""
    real_cte = """
        WITH real AS (
            SELECT u.id AS user_id,
                COALESCE(t_sum.total, 0) + COALESCE(d_sum.total, 0) AS real_donated,
                COALESCE(t_sum.cnt, 0) + COALESCE(d_sum.cnt, 0) AS real_count
            FROM users u
            LEFT JOIN (
                SELECT s.user_id, SUM(t.amount_kopecks) AS total, COUNT(*) AS cnt
                FROM transactions t
                JOIN subscriptions s ON s.id = t.subscription_id
                WHERE t.status = 'success'
                GROUP BY s.user_id
            ) t_sum ON t_sum.user_id = u.id
            LEFT JOIN (
                SELECT user_id, SUM(amount_kopecks) AS total, COUNT(*) AS cnt
                FROM donations WHERE status = 'success'
                GROUP BY user_id
            ) d_sum ON d_sum.user_id = u.id
            WHERE u.is_deleted = false
        )
    """
    async with async_session_factory() as session:
        rows = await session.execute(text(f"""
            {real_cte}
            SELECT r.user_id, u.total_donated_kopecks, r.real_donated,
                   u.total_donations_count, r.real_count
            FROM real r
            JOIN users u ON u.id = r.user_id
            WHERE u.total_donated_kopecks != r.real_donated
               OR u.total_donations_count != r.real_count
        """))
        discrepancies = rows.fetchall()
        for user_id, cached_donated, real_donated, cached_count, real_count in discrepancies:
            logger.warning(
                "reconcile_user_impact_corrected",
                user_id=str(user_id),
                cached_donated=cached_donated, real_donated=real_donated,
                cached_count=cached_count, real_count=real_count,
            )
        if discrepancies:
            await session.execute(text(f"""
                {real_cte}
                UPDATE users u
                SET total_donated_kopecks = r.real_donated,
                    total_donations_count = r.real_count,
                    updated_at = now()
                FROM real r
                WHERE u.id = r.user_id
                  AND (u.total_donated_kopecks != r.real_donated
                       OR u.total_donations_count != r.real_count)
            """))
            await session.commit()
        logger.info("reconcile_user_impact_done", corrected=len(discrepancies))
        return len(discrepancies)
