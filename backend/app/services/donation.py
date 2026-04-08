"""Donation service — create, list, detail."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.exceptions import AppError, BusinessLogicError, NotFoundError
from app.core.logging import get_logger
from app.core.pagination import decode_cursor, encode_cursor
from app.domain.constants import MIN_DONATION_AMOUNT_KOPECKS
from app.models import Campaign, Donation, Foundation, User
from app.models.base import CampaignStatus, DonationSource, DonationStatus, uuid7
from app.services.payment import calculate_fees
from app.services.yookassa import yookassa_client

logger = get_logger(__name__)


async def _check_donation_cooldown(
    session: AsyncSession,
    *,
    user_id: UUID,
    campaign_id: UUID,
) -> None:
    """Enforce minimum interval between successful/pending donations to a campaign.

    Raises AppError with status 429 if the user must wait before donating again.
    """
    cooldown = timedelta(hours=settings.DONATION_COOLDOWN_HOURS)
    if cooldown.total_seconds() <= 0:
        return

    cutoff = datetime.now(timezone.utc) - cooldown
    last_result = await session.execute(
        select(Donation)
        .where(
            Donation.user_id == user_id,
            Donation.campaign_id == campaign_id,
            Donation.is_deleted == False,  # noqa: E712
            Donation.status.in_([DonationStatus.success, DonationStatus.pending]),
            Donation.created_at > cutoff,
        )
        .order_by(Donation.created_at.desc())
        .limit(1)
    )
    last = last_result.scalar_one_or_none()
    if last is None:
        return

    now = datetime.now(timezone.utc)
    next_available = last.created_at + cooldown
    retry_after = max(1, int((next_available - now).total_seconds()))
    raise AppError(
        code="DONATION_COOLDOWN",
        message="В этот сбор можно снова помочь позже.",
        status_code=429,
        details={
            # Both names for backwards compat — prefer next_available_in_seconds
            # in new mobile code, retry_after is the legacy alias.
            "retry_after": retry_after,
            "next_available_in_seconds": retry_after,
            "next_available_at": next_available.isoformat(),
            "server_time_utc": now.isoformat(),
            "last_donation_id": str(last.id),
        },
    )


async def create_donation(
    session: AsyncSession,
    campaign_id: UUID,
    amount_kopecks: int,
    user_id: UUID | None = None,
    email: str | None = None,
    source: DonationSource = DonationSource.app,
    payment_method_id: UUID | None = None,
    save_payment_method: bool = False,
) -> Donation:
    """Create a donation. Authenticated users only — gaste flow is replaced by device-register."""
    result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise NotFoundError("Кампания не найдена")
    if campaign.status != CampaignStatus.active:
        raise BusinessLogicError(code="CAMPAIGN_NOT_ACTIVE", message="Кампания не активна")

    # Auth is now always required — clients should call /auth/device-register first.
    if user_id is None:
        raise AppError(
            code="AUTH_REQUIRED",
            message="Требуется авторизация. Вызовите /auth/device-register при первом запуске приложения.",
            status_code=401,
        )

    # Cooldown: protect against rapid repeat donations to the same campaign.
    await _check_donation_cooldown(session, user_id=user_id, campaign_id=campaign_id)

    if source == DonationSource.app and amount_kopecks < MIN_DONATION_AMOUNT_KOPECKS:
        raise BusinessLogicError(code="MIN_DONATION_AMOUNT", message=f"Минимальная сумма доната: {MIN_DONATION_AMOUNT_KOPECKS} копеек")

    # Resolve saved payment method (if provided) — must belong to the current user.
    provider_pm_id: str | None = None
    if payment_method_id is not None:
        from app.models.payment_method import PaymentMethod  # local import to avoid cycles

        pm_result = await session.execute(
            select(PaymentMethod).where(
                PaymentMethod.id == payment_method_id,
                PaymentMethod.user_id == user_id,
                PaymentMethod.is_deleted == False,  # noqa: E712
            )
        )
        pm = pm_result.scalar_one_or_none()
        if pm is None:
            raise NotFoundError("Способ оплаты не найден")
        provider_pm_id = pm.provider_pm_id

    fees = calculate_fees(amount_kopecks)
    idempotence_key = str(uuid7())

    donation = Donation(
        id=uuid7(),
        user_id=user_id,
        campaign_id=campaign_id,
        foundation_id=campaign.foundation_id,
        amount_kopecks=amount_kopecks,
        platform_fee_kopecks=fees["platform_fee_kopecks"],
        nco_amount_kopecks=fees["nco_amount_kopecks"],
        idempotence_key=idempotence_key,
        status=DonationStatus.pending,
        source=source,
    )
    session.add(donation)
    await session.flush()

    # YooKassa rejects custom URI schemes in return_url, so we use an HTTPS
    # handler page on our backend that opens the porublyu:// deep link via JS.
    # See: GET /payment-result in app/api/v1/payment_result.py
    return_url = f"{settings.PUBLIC_API_URL.rstrip('/')}/payment-result?donation_id={donation.id}"

    # Create YooKassa payment
    payment = await yookassa_client.create_payment(
        amount_kopecks=amount_kopecks,
        description=f"Пожертвование: {campaign.title}"[:128],
        idempotence_key=idempotence_key,
        return_url=return_url,
        save_payment_method=save_payment_method,
        payment_method_id=provider_pm_id,
        metadata={
            "type": "donation",
            "entity_id": str(donation.id),
            "save_payment_method": "1" if save_payment_method else "0",
        },
    )
    donation.provider_payment_id = payment["id"]
    donation.payment_url = payment["payment_url"]
    await session.flush()

    return donation


def _serialize_donation(donation, campaign, foundation) -> dict:
    """Serialize donation with campaign and foundation data."""
    result = {
        "id": donation.id,
        "campaign_id": donation.campaign_id,
        "campaign_title": campaign.title if campaign else None,
        "campaign_status": campaign.status.value if campaign else None,
        "campaign_thumbnail_url": campaign.thumbnail_url if campaign else None,
        "foundation_name": foundation.name if foundation else None,
        "amount_kopecks": donation.amount_kopecks,
        "status": donation.status.value if hasattr(donation.status, "value") else donation.status,
        "source": donation.source.value if hasattr(donation.source, "value") else donation.source,
        "created_at": donation.created_at,
    }
    return result


def _serialize_donation_detail(donation, campaign, foundation) -> dict:
    """Serialize donation detail with full campaign and foundation data."""
    result = _serialize_donation(donation, campaign, foundation)
    result["foundation_id"] = donation.foundation_id
    result["foundation_logo_url"] = foundation.logo_url if foundation else None
    result["payment_url"] = donation.payment_url
    return result


async def list_donations(
    session: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    cursor: str | None = None,
    status: str | None = None,
    campaign_id: UUID | None = None,
) -> dict:
    query = (
        select(Donation, Campaign, Foundation)
        .outerjoin(Campaign, Donation.campaign_id == Campaign.id)
        .outerjoin(Foundation, Donation.foundation_id == Foundation.id)
        .where(Donation.user_id == user_id, Donation.is_deleted == False)  # noqa: E712
        .order_by(Donation.created_at.desc())
    )
    if status:
        query = query.where(Donation.status == status)
    if campaign_id:
        query = query.where(Donation.campaign_id == campaign_id)
    if cursor:
        cursor_data = decode_cursor(cursor)
        query = query.where(Donation.created_at < cursor_data["created_at"])

    result = await session.execute(query.limit(limit + 1))
    rows = result.all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    data = [_serialize_donation(d, c, f) for d, c, f in rows]

    next_cursor = None
    if has_more and rows:
        next_cursor = encode_cursor({"created_at": rows[-1][0].created_at.isoformat()})

    return {"data": data, "has_more": has_more, "next_cursor": next_cursor}


async def get_donation(session: AsyncSession, donation_id: UUID, user_id: UUID) -> dict:
    result = await session.execute(
        select(Donation, Campaign, Foundation)
        .outerjoin(Campaign, Donation.campaign_id == Campaign.id)
        .outerjoin(Foundation, Donation.foundation_id == Foundation.id)
        .where(Donation.id == donation_id, Donation.user_id == user_id, Donation.is_deleted == False)  # noqa: E712
    )
    row = result.first()
    if row is None:
        raise NotFoundError("Донат не найден")
    donation, campaign, foundation = row
    return _serialize_donation_detail(donation, campaign, foundation)
