"""Integration tests for the patron payment-links flow."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.models import Campaign, Donation, PatronPaymentLink, User
from app.models.base import CampaignStatus, DonationSource, DonationStatus, PatronLinkStatus
from app.services.patron import create_payment_link, get_payment_link, list_payment_links
from tests.conftest import create_campaign, create_foundation, create_user


# ---------------------------------------------------------------------------
# create_payment_link
# ---------------------------------------------------------------------------


async def test_create_payment_link_success(
    db: AsyncSession, patron_user: User, campaign: Campaign
):
    """Payment link and associated pending donation are created."""
    link = await create_payment_link(db, patron_user.id, campaign.id, 100000)

    assert link.campaign_id == campaign.id
    assert link.amount_kopecks == 100000
    assert link.status == PatronLinkStatus.pending
    assert link.payment_url is not None

    # Verify underlying donation
    await db.refresh(link)
    from sqlalchemy import select

    donation = (
        await db.execute(select(Donation).where(Donation.id == link.donation_id))
    ).scalar_one()
    assert donation.status == DonationStatus.pending
    assert donation.source == DonationSource.patron_link
    assert donation.amount_kopecks == 100000


async def test_create_payment_link_inactive_campaign(
    db: AsyncSession, patron_user: User, foundation
):
    """Creating a link for an inactive campaign raises CAMPAIGN_NOT_ACTIVE."""
    completed = await create_campaign(db, foundation, status=CampaignStatus.completed)

    with pytest.raises(BusinessLogicError) as exc_info:
        await create_payment_link(db, patron_user.id, completed.id, 50000)

    assert exc_info.value.code == "CAMPAIGN_NOT_ACTIVE"


async def test_create_link_with_any_amount(
    db: AsyncSession, patron_user: User, campaign: Campaign
):
    """Patrons have no minimum donation limit — even small amounts work."""
    link = await create_payment_link(db, patron_user.id, campaign.id, 100)

    assert link.amount_kopecks == 100


# ---------------------------------------------------------------------------
# list / get
# ---------------------------------------------------------------------------


async def test_list_payment_links(
    db: AsyncSession, patron_user: User, campaign: Campaign
):
    """list_payment_links returns only the requesting patron's links."""
    other_patron = await create_user(db, role=patron_user.role)

    l1 = await create_payment_link(db, patron_user.id, campaign.id, 10000)
    l2 = await create_payment_link(db, patron_user.id, campaign.id, 20000)
    _l3 = await create_payment_link(db, other_patron.id, campaign.id, 30000)

    result = await list_payment_links(db, patron_user.id)

    ids = {str(item.id) for item in result["data"]}
    assert str(l1.id) in ids
    assert str(l2.id) in ids
    assert str(_l3.id) not in ids


async def test_get_payment_link_not_found(db: AsyncSession, patron_user: User):
    """Getting a non-existent link raises NotFoundError."""
    with pytest.raises(NotFoundError):
        await get_payment_link(db, uuid7(), patron_user.id)
