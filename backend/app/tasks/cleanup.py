"""§8 — Periodic cleanup tasks.

- OTP codes: hourly, delete expired > 1 hour ago
- Refresh tokens: daily, delete expired > 7 days ago
- Thanks content shown: weekly, delete shown > 90 days ago
- Notification logs: daily, delete > 90 days ago
"""

from sqlalchemy import delete, text

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.tasks import broker

logger = get_logger(__name__)


@broker.task(schedule=[{"cron": "0 * * * *"}])
async def cleanup_otp_codes() -> int:
    """Delete expired OTP codes older than 1 hour."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("DELETE FROM otp_codes WHERE expires_at < now() - interval '1 hour'")
        )
        await session.commit()
        count = result.rowcount
        logger.info("cleanup_otp_codes", deleted=count)
        return count


@broker.task(schedule=[{"cron": "30 3 * * *"}])
async def cleanup_refresh_tokens() -> int:
    """Delete expired refresh tokens older than 7 days (keep for replay audit)."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("DELETE FROM refresh_tokens WHERE expires_at < now() - interval '7 days'")
        )
        await session.commit()
        count = result.rowcount
        logger.info("cleanup_refresh_tokens", deleted=count)
        return count


@broker.task(schedule=[{"cron": "0 4 * * 0"}])
async def cleanup_thanks_content_shown() -> int:
    """Delete thanks_content_shown older than 90 days — allow re-show."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("DELETE FROM thanks_content_shown WHERE shown_at < now() - interval '90 days'")
        )
        await session.commit()
        count = result.rowcount
        logger.info("cleanup_thanks_content_shown", deleted=count)
        return count


@broker.task(schedule=[{"cron": "0 4 * * *"}])
async def cleanup_notification_logs() -> int:
    """Delete notification logs older than 90 days."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("DELETE FROM notification_logs WHERE created_at < now() - interval '90 days'")
        )
        await session.commit()
        count = result.rowcount
        logger.info("cleanup_notification_logs", deleted=count)
        return count
