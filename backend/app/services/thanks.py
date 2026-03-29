"""Thanks content service."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models import ThanksContent, ThanksContentShown

logger = get_logger(__name__)


async def get_thanks_detail(session: AsyncSession, thanks_id: UUID, user_id: UUID) -> dict:
    """Get thanks content with user contribution data."""
    result = await session.execute(
        text("""
            SELECT tc.*, c.title AS campaign_title, c.foundation_id,
                   f.name AS foundation_name
            FROM thanks_contents tc
            JOIN campaigns c ON c.id = tc.campaign_id
            JOIN foundations f ON f.id = c.foundation_id
            WHERE tc.id = :thanks_id
        """),
        {"thanks_id": thanks_id},
    )
    row = result.mappings().first()
    if row is None:
        raise NotFoundError("Благодарность не найдена")

    # Get user contribution to this campaign
    contrib = await session.execute(
        text("""
            SELECT COALESCE(SUM(amount_kopecks), 0) AS total,
                   COUNT(*) AS cnt,
                   MIN(created_at) AS first_at,
                   MAX(created_at) AS last_at
            FROM (
                SELECT amount_kopecks, created_at FROM donations
                WHERE user_id = :user_id AND campaign_id = :campaign_id AND status = 'success' AND is_deleted = false
                UNION ALL
                SELECT t.amount_kopecks, t.created_at FROM transactions t
                JOIN subscriptions s ON s.id = t.subscription_id
                WHERE s.user_id = :user_id AND t.campaign_id = :campaign_id AND t.status = 'success'
            ) combined
        """),
        {"user_id": user_id, "campaign_id": row["campaign_id"]},
    )
    c = contrib.mappings().first()

    # Mark as shown
    await session.execute(
        text("""
            INSERT INTO thanks_content_shown (id, user_id, thanks_content_id)
            VALUES (:id, :user_id, :thanks_id)
            ON CONFLICT (user_id, thanks_content_id) DO NOTHING
        """),
        {"id": uuid7(), "user_id": user_id, "thanks_id": thanks_id},
    )

    return {
        "id": row["id"],
        "campaign_id": row["campaign_id"],
        "campaign_title": row["campaign_title"],
        "foundation_id": row["foundation_id"],
        "foundation_name": row["foundation_name"],
        "type": row["type"],
        "media_url": row["media_url"],
        "title": row["title"],
        "description": row["description"],
        "user_contribution": {
            "total_donated_kopecks": c["total"],
            "donations_count": c["cnt"],
            "first_donation_at": c["first_at"],
            "last_donation_at": c["last_at"],
        },
    }


async def get_unseen_thanks(session: AsyncSession, user_id: UUID) -> list[dict]:
    """Get unseen thanks contents for user."""
    result = await session.execute(
        text("""
            SELECT tc.*, c.title AS campaign_title, f.name AS foundation_name,
                   COALESCE(uc.total, 0) AS user_total,
                   COALESCE(uc.cnt, 0) AS user_count
            FROM thanks_contents tc
            JOIN campaigns c ON c.id = tc.campaign_id
            JOIN foundations f ON f.id = c.foundation_id
            JOIN campaign_donors cd ON cd.campaign_id = tc.campaign_id AND cd.user_id = :user_id
            LEFT JOIN thanks_content_shown tcs ON tcs.thanks_content_id = tc.id AND tcs.user_id = :user_id
            LEFT JOIN LATERAL (
                SELECT SUM(amount_kopecks) AS total, COUNT(*) AS cnt
                FROM (
                    SELECT amount_kopecks FROM donations
                    WHERE user_id = :user_id AND campaign_id = tc.campaign_id AND status = 'success' AND is_deleted = false
                    UNION ALL
                    SELECT t.amount_kopecks FROM transactions t
                    JOIN subscriptions s ON s.id = t.subscription_id
                    WHERE s.user_id = :user_id AND t.campaign_id = tc.campaign_id AND t.status = 'success'
                ) combined
            ) uc ON true
            WHERE tcs.id IS NULL
            ORDER BY tc.created_at DESC
        """),
        {"user_id": user_id},
    )
    rows = result.mappings().all()
    return [
        {
            "id": r["id"],
            "campaign_id": r["campaign_id"],
            "campaign_title": r["campaign_title"],
            "foundation_name": r["foundation_name"],
            "type": r["type"],
            "media_url": r["media_url"],
            "title": r["title"],
            "description": r["description"],
            "user_contribution": {
                "total_donated_kopecks": r["user_total"],
                "donations_count": r["user_count"],
            },
            "created_at": r["created_at"],
        }
        for r in rows
    ]


async def find_unseen_thanks_for_campaign(
    session: AsyncSession, user_id: UUID, campaign_id: UUID
) -> UUID | None:
    """Check if there is an unseen thanks content for this user + campaign.

    Used by the webhook handler after a successful payment to determine
    whether to show a thanks screen.
    """
    result = await session.execute(
        text("""
            SELECT tc.id
            FROM thanks_contents tc
            LEFT JOIN thanks_content_shown tcs
                ON tcs.thanks_content_id = tc.id AND tcs.user_id = :user_id
            WHERE tc.campaign_id = :campaign_id
              AND tcs.id IS NULL
            ORDER BY tc.created_at DESC
            LIMIT 1
        """),
        {"user_id": user_id, "campaign_id": campaign_id},
    )
    row = result.first()
    return row[0] if row else None
