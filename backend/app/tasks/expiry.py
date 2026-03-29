"""§8 — Patron link expiry and campaign auto-close tasks."""

from sqlalchemy import text

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.tasks import broker

logger = get_logger(__name__)


@broker.task(schedule=[{"cron": "15 * * * *"}])
async def expire_patron_links() -> int:
    """Expire pending patron payment links past their expires_at."""
    async with async_session_factory() as session:
        result = await session.execute(text("""
            UPDATE patron_payment_links
            SET status = 'expired'
            WHERE status = 'pending' AND expires_at < now()
        """))
        await session.commit()
        count = result.rowcount
        logger.info("expire_patron_links", expired=count)
        return count


@broker.task(schedule=[{"cron": "0 0 * * *"}])
async def auto_close_expired_campaigns() -> int:
    """CLOSE-05: auto-close campaigns where ends_at <= now, not permanent, still active."""
    async with async_session_factory() as session:
        result = await session.execute(text("""
            UPDATE campaigns
            SET status = 'completed',
                close_note = COALESCE(close_note, 'Сбор завершён по истечении срока.'),
                updated_at = now()
            WHERE ends_at <= now()
              AND status = 'active'
              AND is_permanent = false
        """))
        await session.commit()
        count = result.rowcount
        if count > 0:
            logger.info("auto_close_expired_campaigns", closed=count)
        return count
