"""Campaign service — list, detail, documents, share."""

from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, decode_cursor, encode_cursor, paginated_response
from app.models import Campaign, CampaignDocument, Foundation
from app.models.base import CampaignStatus, FoundationStatus

logger = get_logger(__name__)


async def list_active_campaigns(session: AsyncSession, pagination: PaginationParams) -> dict:
    query = (
        select(Campaign)
        .join(Foundation, Campaign.foundation_id == Foundation.id)
        .options(joinedload(Campaign.foundation))
        .where(Campaign.status == CampaignStatus.active, Foundation.status == FoundationStatus.active)
        .order_by(
            Campaign.urgency_level.desc(),
            case(
                (Campaign.goal_amount > 0, Campaign.collected_amount * 1.0 / Campaign.goal_amount),
                else_=0,
            ).desc(),
            Campaign.sort_order.asc(),
        )
    )
    if pagination.cursor:
        cursor_data = decode_cursor(pagination.cursor)
        query = query.where(Campaign.created_at < cursor_data["created_at"])

    result = await session.execute(query.limit(pagination.limit + 1))
    items = list(result.unique().scalars().all())
    has_more = len(items) > pagination.limit
    items = items[: pagination.limit]

    next_cursor = None
    if has_more and items:
        next_cursor = encode_cursor({"created_at": items[-1].created_at.isoformat()})

    return {"data": items, "has_more": has_more, "next_cursor": next_cursor}


async def get_campaign_detail(session: AsyncSession, campaign_id: UUID) -> Campaign:
    result = await session.execute(
        select(Campaign)
        .options(joinedload(Campaign.foundation), selectinload(Campaign.documents), selectinload(Campaign.thanks_contents))
        .where(Campaign.id == campaign_id, Campaign.status.in_([CampaignStatus.active, CampaignStatus.completed]))
    )
    campaign = result.unique().scalar_one_or_none()
    if campaign is None:
        raise NotFoundError("Кампания не найдена")
    return campaign


async def get_campaign_documents(session: AsyncSession, campaign_id: UUID) -> list[CampaignDocument]:
    result = await session.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.status == CampaignStatus.active)
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Кампания не найдена")

    docs_result = await session.execute(
        select(CampaignDocument)
        .where(CampaignDocument.campaign_id == campaign_id)
        .order_by(CampaignDocument.sort_order)
    )
    return list(docs_result.scalars().all())


async def get_campaign_share(campaign_id: UUID, campaign: Campaign) -> dict:
    return {
        "share_url": f"https://porublyu.ru/campaigns/{campaign_id}",
        "title": campaign.title,
        "description": campaign.description or "",
    }
