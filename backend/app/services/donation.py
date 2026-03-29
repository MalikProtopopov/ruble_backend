"""Donation service — create, list, detail."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import AppError, BusinessLogicError, NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.models import Campaign, Donation, Foundation, User
from app.models.base import CampaignStatus, DonationSource, DonationStatus
from app.domain.constants import MIN_DONATION_AMOUNT_KOPECKS
from app.core.config import settings
from app.services.payment import calculate_fees
from app.services.yookassa import yookassa_client


async def create_donation(
    session: AsyncSession,
    campaign_id: UUID,
    amount_kopecks: int,
    user_id: UUID | None = None,
    email: str | None = None,
    source: DonationSource = DonationSource.app,
) -> Donation:
    """Create a donation. Handles guest flow with email."""
    # Validate campaign
    result = await session.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise NotFoundError("Кампания не найдена")
    if campaign.status != CampaignStatus.active:
        raise BusinessLogicError(code="CAMPAIGN_NOT_ACTIVE", message="Кампания не активна")

    # Handle guest flow — require OTP authentication before donation
    if user_id is None:
        if email is None:
            raise AppError(code="EMAIL_REQUIRED", message="Email обязателен для неавторизованных пользователей", status_code=400)
        user_result = await session.execute(select(User).where(User.email == email, User.is_deleted == False))
        existing_user = user_result.scalar_one_or_none()
        if existing_user is not None:
            if not existing_user.is_active:
                raise AppError(code="ACCOUNT_DEACTIVATED", message="Ваш аккаунт деактивирован", status_code=403)
            raise AppError(
                code="AUTH_REQUIRED",
                message="Пожалуйста, авторизуйтесь для совершения пожертвования.",
                status_code=401,
                details={"email": email},
            )
        # User doesn't exist — client should redirect to OTP registration first
        raise AppError(
            code="AUTH_REQUIRED",
            message="Для совершения пожертвования необходимо зарегистрироваться.",
            status_code=401,
            details={"email": email, "is_new": True},
        )

    if source == DonationSource.app and amount_kopecks < MIN_DONATION_AMOUNT_KOPECKS:
        raise BusinessLogicError(code="MIN_DONATION_AMOUNT", message=f"Минимальная сумма доната: {MIN_DONATION_AMOUNT_KOPECKS} копеек")

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

    # Create YooKassa payment
    payment = await yookassa_client.create_payment(
        amount_kopecks=amount_kopecks,
        description=f"Пожертвование: {campaign.title}"[:128],
        idempotence_key=idempotence_key,
        return_url=f"{settings.PUBLIC_API_URL}/api/v1/donations/{donation.id}/status",
        save_payment_method=False,
        metadata={"type": "donation", "entity_id": str(donation.id)},
    )
    donation.provider_payment_id = payment["id"]
    donation.payment_url = payment["payment_url"]
    await session.flush()

    return donation


async def list_donations(
    session: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    cursor: str | None = None,
    status: str | None = None,
    campaign_id: UUID | None = None,
) -> dict:
    query = (
        select(Donation)
        .where(Donation.user_id == user_id, Donation.is_deleted == False)
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
    items = list(result.scalars().all())
    has_more = len(items) > limit
    items = items[:limit]

    next_cursor = None
    if has_more and items:
        next_cursor = encode_cursor({"created_at": items[-1].created_at.isoformat()})

    return {"data": items, "has_more": has_more, "next_cursor": next_cursor}


async def get_donation(session: AsyncSession, donation_id: UUID, user_id: UUID) -> Donation:
    result = await session.execute(
        select(Donation).where(Donation.id == donation_id, Donation.user_id == user_id, Donation.is_deleted == False)
    )
    donation = result.scalar_one_or_none()
    if donation is None:
        raise NotFoundError("Донат не найден")
    return donation
