"""Campaign service — list, detail, documents, share."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, case, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PaginationParams, decode_cursor, encode_cursor, paginated_response
from app.models import Campaign, CampaignDocument, Donation, Foundation, User
from app.models.base import CampaignStatus, DonationStatus, FoundationStatus

logger = get_logger(__name__)


CAMPAIGN_SORT_DEFAULT = "default"
CAMPAIGN_SORT_HELPED_TODAY = "helped_today"
CAMPAIGN_SORT_HELPED_EVER = "helped_ever"
CAMPAIGN_SORT_MODES = {
    CAMPAIGN_SORT_DEFAULT,
    CAMPAIGN_SORT_HELPED_TODAY,
    CAMPAIGN_SORT_HELPED_EVER,
}


def _build_per_user_subquery(user_id: UUID, user_tz: str):
    """LATERAL subquery: last successful donation of the user in a campaign."""
    return (
        select(
            Donation.id.label("d_id"),
            Donation.amount_kopecks.label("d_amount"),
            Donation.created_at.label("d_created_at"),
            Donation.status.label("d_status"),
        )
        .where(
            Donation.user_id == user_id,
            Donation.campaign_id == Campaign.id,
            Donation.status == DonationStatus.success,
            Donation.is_deleted == False,  # noqa: E712
        )
        .order_by(Donation.created_at.desc())
        .limit(1)
        .correlate(Campaign)
        .lateral("last_don")
    )


async def list_campaigns(
    session: AsyncSession,
    pagination: PaginationParams,
    *,
    status: str | None = None,
    user: User | None = None,
    sort: str | None = None,
) -> dict:
    if status and status in ("active", "completed"):
        filter_status = CampaignStatus(status)
    else:
        filter_status = CampaignStatus.active

    sort_mode = sort if sort in CAMPAIGN_SORT_MODES else CAMPAIGN_SORT_DEFAULT

    # Non-authenticated path: simple query (no per-user enrichment).
    if user is None:
        query = (
            select(Campaign)
            .join(Foundation, Campaign.foundation_id == Foundation.id)
            .options(joinedload(Campaign.foundation))
            .where(Campaign.status == filter_status, Foundation.status == FoundationStatus.active)
        )
        if filter_status == CampaignStatus.active:
            query = query.order_by(
                Campaign.urgency_level.desc(),
                case(
                    (Campaign.goal_amount > 0, Campaign.collected_amount * 1.0 / Campaign.goal_amount),
                    else_=0,
                ).desc(),
                Campaign.sort_order.asc(),
            )
        else:
            query = query.order_by(Campaign.updated_at.desc())

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
        return {"data": items, "has_more": has_more, "next_cursor": next_cursor, "with_user_data": False}

    # Authenticated path: join with last donation for per-user fields.
    user_tz = user.timezone or "Europe/Moscow"
    last_don = _build_per_user_subquery(user.id, user_tz)

    # donated_today: was there a successful donation today in the user's timezone?
    from sqlalchemy import func as sa_func

    donated_today_expr = case(
        (
            last_don.c.d_created_at.is_not(None),
            sa_func.date(sa_func.timezone(user_tz, last_don.c.d_created_at))
            == sa_func.date(sa_func.timezone(user_tz, sa_func.now())),
        ),
        else_=literal(False),
    )

    has_any_expr = last_don.c.d_id.is_not(None)

    query = (
        select(
            Campaign,
            last_don.c.d_id,
            last_don.c.d_amount,
            last_don.c.d_created_at,
            last_don.c.d_status,
            donated_today_expr.label("donated_today"),
            has_any_expr.label("has_any_donation"),
        )
        .join(Foundation, Campaign.foundation_id == Foundation.id)
        .outerjoin(last_don, literal(True))
        .options(joinedload(Campaign.foundation))
        .where(Campaign.status == filter_status, Foundation.status == FoundationStatus.active)
    )

    if sort_mode == CAMPAIGN_SORT_HELPED_TODAY:
        query = query.order_by(
            donated_today_expr.desc(),
            has_any_expr.desc(),
            Campaign.urgency_level.desc(),
            Campaign.sort_order.asc(),
        )
    elif sort_mode == CAMPAIGN_SORT_HELPED_EVER:
        query = query.order_by(
            has_any_expr.desc(),
            Campaign.urgency_level.desc(),
            Campaign.sort_order.asc(),
        )
    elif filter_status == CampaignStatus.active:
        query = query.order_by(
            Campaign.urgency_level.desc(),
            case(
                (Campaign.goal_amount > 0, Campaign.collected_amount * 1.0 / Campaign.goal_amount),
                else_=0,
            ).desc(),
            Campaign.sort_order.asc(),
        )
    else:
        query = query.order_by(Campaign.updated_at.desc())

    if pagination.cursor:
        cursor_data = decode_cursor(pagination.cursor)
        query = query.where(Campaign.created_at < cursor_data["created_at"])

    result = await session.execute(query.limit(pagination.limit + 1))
    rows = result.unique().all()
    has_more = len(rows) > pagination.limit
    rows = rows[: pagination.limit]

    cooldown = timedelta(hours=settings.DONATION_COOLDOWN_HOURS)
    now = datetime.now(timezone.utc)

    items: list[dict] = []
    for row in rows:
        campaign = row[0]
        d_id = row[1]
        d_amount = row[2]
        d_created_at = row[3]
        d_status = row[4]
        donated_today = bool(row[5]) if row[5] is not None else False
        has_any_donation = bool(row[6])

        last_donation = None
        next_available_at = None
        if d_id is not None:
            last_donation = {
                "id": d_id,
                "amount_kopecks": d_amount,
                "created_at": d_created_at,
                "status": d_status.value if hasattr(d_status, "value") else d_status,
            }
            next_at = d_created_at + cooldown
            if next_at > now:
                next_available_at = next_at

        items.append(
            {
                "campaign": campaign,
                "donated_today": donated_today,
                "has_any_donation": has_any_donation,
                "last_donation": last_donation,
                "next_available_at": next_available_at,
            }
        )

    next_cursor = None
    if has_more and items:
        next_cursor = encode_cursor({"created_at": items[-1]["campaign"].created_at.isoformat()})

    return {"data": items, "has_more": has_more, "next_cursor": next_cursor, "with_user_data": True}


async def list_today_campaigns(
    session: AsyncSession,
    *,
    user: User | None,
    limit: int = 3,
) -> list:
    """Top-N active campaigns curated for the 'today' widget on the mobile home screen."""
    pagination = PaginationParams(limit=limit, cursor=None)
    result = await list_campaigns(
        session,
        pagination,
        status="active",
        user=user,
        sort=CAMPAIGN_SORT_DEFAULT,
    )
    return result["data"]


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


async def get_user_campaign_state(
    session: AsyncSession, *, user_id: UUID, campaign_id: UUID,
) -> dict:
    """Compute donated_today / has_any_donation / last_donation / next_available_at
    for a single (user, campaign) pair. Used by the campaign detail endpoint."""
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    user_tz = user.timezone if user else "Europe/Moscow"

    last_result = await session.execute(
        select(Donation)
        .where(
            Donation.user_id == user_id,
            Donation.campaign_id == campaign_id,
            Donation.status == DonationStatus.success,
            Donation.is_deleted == False,  # noqa: E712
        )
        .order_by(Donation.created_at.desc())
        .limit(1)
    )
    last = last_result.scalar_one_or_none()

    cooldown = timedelta(hours=settings.DONATION_COOLDOWN_HOURS)
    now = datetime.now(timezone.utc)
    state = {
        "donated_today": False,
        "has_any_donation": False,
        "last_donation": None,
        "next_available_at": None,
    }
    if last is None:
        return state

    state["has_any_donation"] = True
    state["last_donation"] = {
        "id": last.id,
        "amount_kopecks": last.amount_kopecks,
        "created_at": last.created_at,
        "status": last.status.value if hasattr(last.status, "value") else last.status,
    }
    next_at = last.created_at + cooldown
    if next_at > now:
        state["next_available_at"] = next_at

    # donated_today: compare dates in user's timezone
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(user_tz)
        state["donated_today"] = last.created_at.astimezone(tz).date() == now.astimezone(tz).date()
    except Exception:
        state["donated_today"] = False

    return state


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
