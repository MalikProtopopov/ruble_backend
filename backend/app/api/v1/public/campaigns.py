"""Public campaign endpoints (no auth required for list/detail/documents)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import require_donor
from app.schemas.campaign import (
    CampaignDetailResponse,
    CampaignDocumentResponse,
    CampaignListItem,
    ShareResponse,
)
from app.services import campaign as campaign_service

router = APIRouter(tags=["campaigns"])


@router.get("", summary="List active campaigns", description="Лента активных кампаний с пагинацией")
async def list_campaigns(
    pagination: PaginationParams = Depends(get_pagination),
    session: AsyncSession = Depends(get_db_session),
):
    result = await campaign_service.list_active_campaigns(session, pagination)
    return paginated_response(result["data"], result["next_cursor"], result["has_more"])


@router.get("/{campaign_id}", response_model=CampaignDetailResponse, summary="Get campaign detail", description="Детальная информация о кампании")
async def get_campaign(
    campaign_id: UUID,
    session: AsyncSession = Depends(get_db_session),
):
    return await campaign_service.get_campaign_detail(session, campaign_id)


@router.get("/{campaign_id}/documents", response_model=list[CampaignDocumentResponse], summary="Get campaign documents", description="Документы кампании")
async def get_campaign_documents(
    campaign_id: UUID,
    session: AsyncSession = Depends(get_db_session),
):
    return await campaign_service.get_campaign_documents(session, campaign_id)


@router.get("/{campaign_id}/share", response_model=ShareResponse, summary="Get campaign share data", description="Данные для шаринга кампании в соцсетях")
async def get_campaign_share(
    campaign_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_donor),
):
    campaign = await campaign_service.get_campaign_detail(session, campaign_id)
    return await campaign_service.get_campaign_share(campaign_id, campaign)
