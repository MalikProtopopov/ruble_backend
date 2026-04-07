"""Donation cooldown reminder push.

Once per hour, finds users whose donation cooldown to a campaign just expired
(within the last hour) and who have not yet donated again. Sends a one-shot
reminder push so they come back to the campaign feed.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.services.notification import send_push
from app.tasks import broker

logger = get_logger(__name__)


@broker.task(schedule=[{"cron": "5 * * * *"}])
async def send_donation_reminders() -> int:
    """Send a reminder push to users whose donation cooldown to a campaign just expired."""
    cooldown_h = settings.DONATION_COOLDOWN_HOURS
    if cooldown_h <= 0:
        return 0

    now = datetime.now(timezone.utc)
    # We want donations whose (created_at + cooldown) is in the last hour AND
    # the user has not donated again to the same campaign since.
    window_start = now - timedelta(hours=cooldown_h, minutes=60)
    window_end = now - timedelta(hours=cooldown_h)

    sent = 0
    async with async_session_factory() as session:
        rows = await session.execute(
            text(
                """
                SELECT DISTINCT ON (d.user_id, d.campaign_id)
                    d.user_id,
                    d.campaign_id,
                    c.title AS campaign_title,
                    u.push_token,
                    u.notification_preferences
                FROM donations d
                JOIN users u ON u.id = d.user_id
                JOIN campaigns c ON c.id = d.campaign_id
                WHERE d.status = 'success'
                  AND d.is_deleted = false
                  AND d.created_at BETWEEN :w_start AND :w_end
                  AND u.is_deleted = false
                  AND u.is_active = true
                  AND u.push_token IS NOT NULL
                  AND c.status = 'active'
                  AND COALESCE((u.notification_preferences->>'push_on_donation_reminder')::boolean, true) = true
                  AND NOT EXISTS (
                      SELECT 1 FROM donations d2
                      WHERE d2.user_id = d.user_id
                        AND d2.campaign_id = d.campaign_id
                        AND d2.created_at > d.created_at
                        AND d2.status IN ('success', 'pending')
                        AND d2.is_deleted = false
                  )
                ORDER BY d.user_id, d.campaign_id, d.created_at DESC
                LIMIT 1000
                """
            ),
            {"w_start": window_start, "w_end": window_end},
        )

        for user_id, campaign_id, title, push_token, _prefs in rows.fetchall():
            short_title = (title or "")[:48]
            await send_push(
                session,
                user_id=user_id,
                push_token=push_token,
                notification_type="donation_reminder",
                title="Можно снова поддержать сбор",
                body=f"«{short_title}» ждёт вашей помощи.",
                data={
                    "type": "donation_reminder",
                    "campaign_id": str(campaign_id),
                },
            )
            sent += 1

        await session.commit()
    logger.info("donation_reminders_sent", sent=sent)
    return sent
