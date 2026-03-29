"""Subscription limit check — §5 rule 3.

Max 5 active subscriptions per user.
Uses SELECT COUNT FOR UPDATE inside a transaction.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessLogicError
from app.domain.constants import MAX_ACTIVE_SUBSCRIPTIONS


async def check_subscription_limit(session: AsyncSession, user_id: UUID) -> None:
    """Raise SUBSCRIPTION_LIMIT_EXCEEDED if user already has max active subscriptions.

    Must be called inside a transaction. Uses FOR UPDATE to prevent race conditions.
    """
    # Lock the matching rows first, then count them.
    # FOR UPDATE cannot be used with aggregate functions directly.
    result = await session.execute(
        text("""
            SELECT COUNT(*) FROM (
                SELECT id
                FROM subscriptions
                WHERE user_id = :user_id
                  AND status IN ('active', 'paused', 'pending_payment_method')
                  AND is_deleted = false
                FOR UPDATE
            ) locked
        """),
        {"user_id": user_id},
    )
    count = result.scalar_one()
    if count >= MAX_ACTIVE_SUBSCRIPTIONS:
        raise BusinessLogicError(
            code="SUBSCRIPTION_LIMIT_EXCEEDED",
            message=f"Максимальное количество активных подписок ({MAX_ACTIVE_SUBSCRIPTIONS}) достигнуто",
        )
