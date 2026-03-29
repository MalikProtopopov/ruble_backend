"""§8 — Daily reconciliation tasks.

Compares denormalized counters with real data. Logs discrepancies, does NOT auto-correct.
"""

from sqlalchemy import text

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.tasks import broker

logger = get_logger(__name__)


@broker.task(schedule=[{"cron": "0 5 * * *"}])
async def reconcile_collected_amount() -> int:
    """Compare campaigns.collected_amount with SUM of success transactions + donations + offline."""
    async with async_session_factory() as session:
        rows = await session.execute(text("""
            WITH real AS (
                SELECT c.id AS campaign_id,
                    COALESCE(t_sum.total, 0)
                    + COALESCE(d_sum.total, 0)
                    + COALESCE(o_sum.total, 0) AS real_amount
                FROM campaigns c
                LEFT JOIN (
                    SELECT campaign_id, SUM(amount_kopecks) AS total
                    FROM transactions WHERE status = 'success'
                    GROUP BY campaign_id
                ) t_sum ON t_sum.campaign_id = c.id
                LEFT JOIN (
                    SELECT campaign_id, SUM(amount_kopecks) AS total
                    FROM donations WHERE status = 'success'
                    GROUP BY campaign_id
                ) d_sum ON d_sum.campaign_id = c.id
                LEFT JOIN (
                    SELECT campaign_id, SUM(amount_kopecks) AS total
                    FROM offline_payments
                    GROUP BY campaign_id
                ) o_sum ON o_sum.campaign_id = c.id
            )
            SELECT r.campaign_id, c.collected_amount, r.real_amount
            FROM real r
            JOIN campaigns c ON c.id = r.campaign_id
            WHERE c.collected_amount != r.real_amount
        """))
        discrepancies = rows.fetchall()
        for campaign_id, cached, real in discrepancies:
            logger.warning(
                "reconcile_collected_amount_mismatch",
                campaign_id=str(campaign_id),
                cached=cached,
                real=real,
                diff=cached - real,
            )
        logger.info("reconcile_collected_amount_done", discrepancies=len(discrepancies))
        return len(discrepancies)


@broker.task(schedule=[{"cron": "5 5 * * *"}])
async def reconcile_donors_count() -> int:
    """Compare campaigns.donors_count with COUNT from campaign_donors."""
    async with async_session_factory() as session:
        rows = await session.execute(text("""
            SELECT c.id, c.donors_count, COALESCE(cd.cnt, 0) AS real_count
            FROM campaigns c
            LEFT JOIN (
                SELECT campaign_id, COUNT(*) AS cnt
                FROM campaign_donors
                GROUP BY campaign_id
            ) cd ON cd.campaign_id = c.id
            WHERE c.donors_count != COALESCE(cd.cnt, 0)
        """))
        discrepancies = rows.fetchall()
        for campaign_id, cached, real in discrepancies:
            logger.warning(
                "reconcile_donors_count_mismatch",
                campaign_id=str(campaign_id),
                cached=cached,
                real=real,
            )
        logger.info("reconcile_donors_count_done", discrepancies=len(discrepancies))
        return len(discrepancies)


@broker.task(schedule=[{"cron": "10 5 * * *"}])
async def reconcile_user_impact() -> int:
    """Compare users.total_donated_kopecks / total_donations_count with real data."""
    async with async_session_factory() as session:
        rows = await session.execute(text("""
            WITH real AS (
                SELECT u.id AS user_id,
                    COALESCE(t_sum.total, 0) + COALESCE(d_sum.total, 0) AS real_donated,
                    COALESCE(t_sum.cnt, 0) + COALESCE(d_sum.cnt, 0) AS real_count
                FROM users u
                LEFT JOIN (
                    SELECT s.user_id,
                        SUM(t.amount_kopecks) AS total,
                        COUNT(*) AS cnt
                    FROM transactions t
                    JOIN subscriptions s ON s.id = t.subscription_id
                    WHERE t.status = 'success'
                    GROUP BY s.user_id
                ) t_sum ON t_sum.user_id = u.id
                LEFT JOIN (
                    SELECT user_id,
                        SUM(amount_kopecks) AS total,
                        COUNT(*) AS cnt
                    FROM donations WHERE status = 'success'
                    GROUP BY user_id
                ) d_sum ON d_sum.user_id = u.id
                WHERE u.is_deleted = false
            )
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
                "reconcile_user_impact_mismatch",
                user_id=str(user_id),
                cached_donated=cached_donated,
                real_donated=real_donated,
                cached_count=cached_count,
                real_count=real_count,
            )
        logger.info("reconcile_user_impact_done", discrepancies=len(discrepancies))
        return len(discrepancies)
