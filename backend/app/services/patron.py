"""Patron payment links service."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.core.pagination import decode_cursor, encode_cursor
from app.models import Campaign, Donation, PatronPaymentLink
from app.models.base import CampaignStatus, DonationSource, DonationStatus, PatronLinkStatus
from app.services.payment import calculate_fees

PATRON_LINK_TTL_HOURS = 24


async def create_payment_link(session: AsyncSession, user_id: UUID, campaign_id: UUID, amount_kopecks: int) -> PatronPaymentLink:
    result = await session.execute(select(Campaign).where(Campaign.id == campaign_id, Campaign.status == CampaignStatus.active))
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise BusinessLogicError(code="CAMPAIGN_NOT_ACTIVE", message="Кампания не активна")

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
        source=DonationSource.patron_link,
        status=DonationStatus.pending,
    )
    session.add(donation)
    await session.flush()

    # TODO: create YooKassa payment
    payment_url = f"https://yookassa.ru/pay/{idempotence_key}"

    link = PatronPaymentLink(
        id=uuid7(),
        campaign_id=campaign_id,
        created_by_user_id=user_id,
        amount_kopecks=amount_kopecks,
        donation_id=donation.id,
        payment_url=payment_url,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=PATRON_LINK_TTL_HOURS),
    )
    session.add(link)
    await session.flush()
    return link


async def list_payment_links(
    session: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    cursor: str | None = None,
    status: str | None = None,
) -> dict:
    query = (
        select(PatronPaymentLink)
        .where(PatronPaymentLink.created_by_user_id == user_id)
        .order_by(PatronPaymentLink.created_at.desc())
    )
    if status:
        query = query.where(PatronPaymentLink.status == status)
    if cursor:
        cursor_data = decode_cursor(cursor)
        query = query.where(PatronPaymentLink.created_at < cursor_data["created_at"])

    result = await session.execute(query.limit(limit + 1))
    items = list(result.scalars().all())
    has_more = len(items) > limit
    items = items[:limit]
    next_cursor = encode_cursor({"created_at": items[-1].created_at.isoformat()}) if has_more and items else None

    return {"data": items, "has_more": has_more, "next_cursor": next_cursor}


async def get_payment_link(session: AsyncSession, link_id: UUID, user_id: UUID) -> PatronPaymentLink:
    result = await session.execute(
        select(PatronPaymentLink).where(PatronPaymentLink.id == link_id, PatronPaymentLink.created_by_user_id == user_id)
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise NotFoundError("Ссылка не найдена")
    return link
