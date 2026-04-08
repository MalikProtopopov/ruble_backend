"""Public campaign endpoints (no auth required for list/detail/documents)."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.pagination import PaginationParams, get_pagination, paginated_response
from app.core.security import bearer_scheme, decode_token, require_donor
from app.models import User
from app.schemas.campaign import (
    CampaignDetailResponse,
    CampaignDocumentResponse,
    CampaignListItem,
    LastDonationBrief,
    ShareResponse,
)
from app.services import campaign as campaign_service

router = APIRouter(tags=["campaigns"])


async def _resolve_optional_user(
    session: AsyncSession,
    credentials: HTTPAuthorizationCredentials | None,
) -> User | None:
    """Decode bearer token if present and load the user. Returns None on any failure."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            return None
        user_id = UUID(payload["sub"])
    except Exception:
        return None
    result = await session.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)  # noqa: E712
    )
    return result.scalar_one_or_none()


def _serialize_campaign_item(
    campaign,
    *,
    donated_today=None,
    has_any_donation=None,
    last_donation=None,
    next_available_at=None,
    is_authenticated: bool = False,
) -> CampaignListItem:
    """Build a CampaignListItem from a Campaign ORM object plus optional per-user fields.

    Computes the server-side cooldown helpers (can_donate_now,
    next_available_in_seconds, server_time_utc) so the mobile client never has
    to parse timestamps or compute time deltas locally.
    """
    last_dto = None
    if last_donation is not None:
        last_dto = LastDonationBrief(
            id=last_donation["id"],
            amount_kopecks=last_donation["amount_kopecks"],
            created_at=last_donation["created_at"],
            status=last_donation["status"],
        )

    # Server-computed cooldown helpers. Only populated for authenticated
    # requests — for guests they stay None, mirroring the other per-user fields.
    can_donate_now: bool | None = None
    next_available_in_seconds: int | None = None
    server_time_utc: datetime | None = None
    if is_authenticated:
        server_time_utc = datetime.now(timezone.utc)
        if next_available_at is None:
            can_donate_now = True
        else:
            delta = (next_available_at - server_time_utc).total_seconds()
            if delta <= 0:
                # Cooldown already expired between query and serialization.
                can_donate_now = True
                next_available_in_seconds = None
            else:
                can_donate_now = False
                next_available_in_seconds = int(delta)

    return CampaignListItem(
        id=campaign.id,
        foundation_id=campaign.foundation_id,
        foundation=campaign.foundation,
        title=campaign.title,
        description=campaign.description,
        thumbnail_url=campaign.thumbnail_url,
        status=campaign.status.value if hasattr(campaign.status, "value") else campaign.status,
        goal_amount=campaign.goal_amount,
        collected_amount=campaign.collected_amount,
        donors_count=campaign.donors_count,
        urgency_level=campaign.urgency_level,
        is_permanent=campaign.is_permanent,
        ends_at=campaign.ends_at,
        created_at=campaign.created_at,
        donated_today=donated_today,
        has_any_donation=has_any_donation,
        last_donation=last_dto,
        next_available_at=next_available_at,
        can_donate_now=can_donate_now,
        next_available_in_seconds=next_available_in_seconds,
        server_time_utc=server_time_utc,
    )


def _serialize_list_result(result: dict) -> list[CampaignListItem]:
    if result.get("with_user_data"):
        return [
            _serialize_campaign_item(
                row["campaign"],
                donated_today=row["donated_today"],
                has_any_donation=row["has_any_donation"],
                last_donation=row["last_donation"],
                next_available_at=row["next_available_at"],
                is_authenticated=True,
            )
            for row in result["data"]
        ]
    return [_serialize_campaign_item(c) for c in result["data"]]


@router.get(
    "",
    summary="List campaigns",
    description=(
        "Лента кампаний с пагинацией и фильтром по статусу. "
        "Если запрос авторизован — возвращает дополнительные per-user поля "
        "(donated_today, last_donation, next_available_at) и поддерживает sort=helped_today|helped_ever."
    ),
)
async def list_campaigns(
    status: str | None = Query(default=None, description="active | completed (default: active)"),
    sort: str | None = Query(default=None, description="default | helped_today | helped_ever"),
    pagination: PaginationParams = Depends(get_pagination),
    session: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    user = await _resolve_optional_user(session, credentials)
    result = await campaign_service.list_campaigns(
        session, pagination, status=status, user=user, sort=sort,
    )
    items = _serialize_list_result(result)
    return paginated_response(items, result["next_cursor"], result["has_more"])


@router.get(
    "/today",
    response_model=list[CampaignListItem],
    summary="Featured campaigns for today",
    description="Топ-3 активных сбора для виджета 'Сегодня помогаем' на главном экране.",
)
async def list_campaigns_today(
    session: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    user = await _resolve_optional_user(session, credentials)
    rows = await campaign_service.list_today_campaigns(session, user=user, limit=3)
    if user is None:
        return [_serialize_campaign_item(c) for c in rows]
    return [
        _serialize_campaign_item(
            row["campaign"],
            donated_today=row["donated_today"],
            has_any_donation=row["has_any_donation"],
            last_donation=row["last_donation"],
            next_available_at=row["next_available_at"],
            is_authenticated=True,
        )
        for row in rows
    ]


@router.get("/{campaign_id}", response_model=CampaignDetailResponse, summary="Get campaign detail", description="Детальная информация о кампании. Per-user поля заполняются если запрос авторизован.")
async def get_campaign(
    campaign_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    from app.core.config import settings
    campaign = await campaign_service.get_campaign_detail(session, campaign_id)
    user = await _resolve_optional_user(session, credentials)

    state = {
        "donated_today": None,
        "has_any_donation": None,
        "last_donation": None,
        "next_available_at": None,
    }
    if user is not None:
        state = await campaign_service.get_user_campaign_state(
            session, user_id=user.id, campaign_id=campaign_id,
        )

    last_dto = None
    if state["last_donation"] is not None:
        last_dto = LastDonationBrief(**state["last_donation"])

    # Server-computed cooldown helpers — same logic as the list endpoint, but
    # CampaignDetailResponse is built manually here, so we duplicate the math.
    can_donate_now: bool | None = None
    next_available_in_seconds: int | None = None
    server_time_utc: datetime | None = None
    if user is not None:
        server_time_utc = datetime.now(timezone.utc)
        next_at = state["next_available_at"]
        if next_at is None:
            can_donate_now = True
        else:
            delta = (next_at - server_time_utc).total_seconds()
            if delta <= 0:
                can_donate_now = True
            else:
                can_donate_now = False
                next_available_in_seconds = int(delta)

    return CampaignDetailResponse(
        id=campaign.id,
        foundation_id=campaign.foundation_id,
        foundation=campaign.foundation,
        title=campaign.title,
        description=campaign.description,
        thumbnail_url=campaign.thumbnail_url,
        status=campaign.status.value if hasattr(campaign.status, "value") else campaign.status,
        goal_amount=campaign.goal_amount,
        collected_amount=campaign.collected_amount,
        donors_count=campaign.donors_count,
        urgency_level=campaign.urgency_level,
        is_permanent=campaign.is_permanent,
        ends_at=campaign.ends_at,
        created_at=campaign.created_at,
        donated_today=state["donated_today"],
        has_any_donation=state["has_any_donation"],
        last_donation=last_dto,
        next_available_at=state["next_available_at"],
        can_donate_now=can_donate_now,
        next_available_in_seconds=next_available_in_seconds,
        server_time_utc=server_time_utc,
        video_url=campaign.video_url,
        closed_early=campaign.closed_early,
        close_note=campaign.close_note,
        documents=campaign.documents,
        thanks_contents=campaign.thanks_contents,
        cooldown_hours=settings.DONATION_COOLDOWN_HOURS,
    )


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
