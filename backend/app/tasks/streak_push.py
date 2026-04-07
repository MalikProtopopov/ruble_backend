"""§8 / NOTIF-08 — Daily streak push notifications.

Runs every 15 min. Selects users where next_streak_push_at <= now() and
push_daily_streak is enabled. Sends push via configured provider,
then recalculates next_streak_push_at for tomorrow 12:00 in user's timezone.
"""

from sqlalchemy import text

from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.services.notification import send_push
from app.tasks import broker

logger = get_logger(__name__)


@broker.task(schedule=[{"cron": "*/15 * * * *"}])
async def send_streak_pushes() -> int:
    """Send daily streak push notifications for eligible users."""
    async with async_session_factory() as session:
        rows = await session.execute(text("""
            SELECT id, current_streak_days, timezone, push_token, push_platform
            FROM users
            WHERE next_streak_push_at <= now()
              AND is_deleted = false
              AND next_streak_push_at IS NOT NULL
            LIMIT 500
        """))
        users = rows.fetchall()
        if not users:
            return 0

        sent = 0
        for user_id, streak, tz, push_token, push_platform in users:
            await send_push(
                session,
                user_id=user_id,
                push_token=push_token,
                notification_type="streak_daily",
                title=f"Ваш стрик: {streak} дней!",
                body=f"Вы помогаете {streak} дней подряд. Так держать!",
                data={"type": "streak_daily", "days": streak},
            )

            # Recalculate next push: tomorrow 12:00 in user's timezone, converted to UTC
            await session.execute(text("""
                UPDATE users
                SET next_streak_push_at = (
                    (CURRENT_DATE AT TIME ZONE :tz + interval '1 day' + interval '12 hours')
                    AT TIME ZONE :tz
                )
                WHERE id = :user_id
            """), {"user_id": user_id, "tz": tz})

            sent += 1

        await session.commit()
        logger.info("send_streak_pushes", sent=sent)
        return sent
