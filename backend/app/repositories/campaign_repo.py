"""Campaign repository — all DB operations for campaigns."""

from uuid import UUID

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.pagination import PaginationParams
from app.models import Campaign, CampaignDocument, Foundation, OfflinePayment, Subscription, ThanksContent
from app.models.base import CampaignStatus, FoundationStatus, SubscriptionStatus, uuid7
from app.repositories.base import cursor_paginate


async def get_by_id(session: AsyncSession, campaign_id: UUID, *, with_relations: bool = False) -> Campaign | None:
    """Get campaign by ID, optionally with documents and thanks_contents."""
    query = select(Campaign).options(joinedload(Campaign.foundation))
    if with_relations:
        query = query.options(selectinload(Campaign.documents), selectinload(Campaign.thanks_contents))
    result = await session.execute(query.where(Campaign.id == campaign_id))
    return result.unique().scalar_one_or_none()


async def list_admin(
    session: AsyncSession,
    pagination: PaginationParams,
    *,
    status: str | None = None,
    foundation_id: UUID | None = None,
    search: str | None = None,
) -> dict:
    """List campaigns for admin panel with filters."""
    query = select(Campaign).options(joinedload(Campaign.foundation))
    if status:
        query = query.where(Campaign.status == status)
    if foundation_id:
        query = query.where(Campaign.foundation_id == foundation_id)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Campaign.title.ilike(pattern), Campaign.description.ilike(pattern)))
    return await cursor_paginate(session, query, Campaign, pagination)


async def create(session: AsyncSession, **kwargs) -> Campaign:
    campaign = Campaign(id=uuid7(), **kwargs)
    session.add(campaign)
    await session.flush()
    await session.refresh(campaign)
    return campaign


async def update(session: AsyncSession, campaign: Campaign, data: dict) -> Campaign:
    for field, value in data.items():
        setattr(campaign, field, value)
    await session.flush()
    await session.refresh(campaign)
    return campaign


async def atomic_increment_collected(session: AsyncSession, campaign_id: UUID, amount: int) -> None:
    """Atomically increment collected_amount using raw SQL."""
    await session.execute(
        text("UPDATE campaigns SET collected_amount = collected_amount + :amount, updated_at = now() WHERE id = :cid"),
        {"amount": amount, "cid": campaign_id},
    )


# --- Documents ---


async def add_document(session: AsyncSession, campaign_id: UUID, title: str, file_url: str, sort_order: int = 0) -> CampaignDocument:
    doc = CampaignDocument(id=uuid7(), campaign_id=campaign_id, title=title, file_url=file_url, sort_order=sort_order)
    session.add(doc)
    await session.flush()
    return doc


async def get_document(session: AsyncSession, campaign_id: UUID, doc_id: UUID) -> CampaignDocument | None:
    result = await session.execute(
        select(CampaignDocument).where(CampaignDocument.id == doc_id, CampaignDocument.campaign_id == campaign_id)
    )
    return result.scalar_one_or_none()


async def delete_document(session: AsyncSession, doc: CampaignDocument) -> None:
    await session.delete(doc)
    await session.flush()


# --- Thanks Content ---


async def add_thanks(session: AsyncSession, campaign_id: UUID, **kwargs) -> ThanksContent:
    thanks = ThanksContent(id=uuid7(), campaign_id=campaign_id, **kwargs)
    session.add(thanks)
    await session.flush()
    return thanks


async def get_thanks(session: AsyncSession, campaign_id: UUID, thanks_id: UUID) -> ThanksContent | None:
    result = await session.execute(
        select(ThanksContent).where(ThanksContent.id == thanks_id, ThanksContent.campaign_id == campaign_id)
    )
    return result.scalar_one_or_none()


async def delete_thanks(session: AsyncSession, thanks: ThanksContent) -> None:
    await session.delete(thanks)
    await session.flush()


# --- Offline Payments ---


async def create_offline_payment(session: AsyncSession, **kwargs) -> OfflinePayment:
    payment = OfflinePayment(id=uuid7(), **kwargs)
    session.add(payment)
    await session.flush()
    return payment


async def find_duplicate_offline_payment(
    session: AsyncSession, campaign_id: UUID, external_reference: str, payment_date, amount_kopecks: int
) -> bool:
    result = await session.execute(
        select(OfflinePayment).where(
            OfflinePayment.campaign_id == campaign_id,
            OfflinePayment.external_reference == external_reference,
            OfflinePayment.payment_date == payment_date,
            OfflinePayment.amount_kopecks == amount_kopecks,
        )
    )
    return result.scalar_one_or_none() is not None


async def list_offline_payments(session: AsyncSession, campaign_id: UUID, pagination: PaginationParams) -> dict:
    query = select(OfflinePayment).where(OfflinePayment.campaign_id == campaign_id)
    return await cursor_paginate(session, query, OfflinePayment, pagination)


# --- Active subscriptions ---


async def get_active_subscriptions(session: AsyncSession, campaign_id: UUID) -> list[Subscription]:
    result = await session.execute(
        select(Subscription).where(
            Subscription.campaign_id == campaign_id,
            Subscription.status == SubscriptionStatus.active,
        )
    )
    return list(result.scalars().all())
