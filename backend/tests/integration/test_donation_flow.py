"""Integration tests for the donation flow."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import AppError, BusinessLogicError, NotFoundError
from app.models import Campaign, Donation, User
from app.models.base import CampaignStatus, DonationStatus
from app.services.donation import create_donation, get_donation, list_donations
from tests.conftest import create_campaign, create_foundation, create_user


# ---------------------------------------------------------------------------
# create_donation
# ---------------------------------------------------------------------------


async def test_create_donation_success(db: AsyncSession, user: User, campaign: Campaign):
    """Donation is created with pending status and correct fee split."""
    donation = await create_donation(db, campaign.id, 10000, user_id=user.id)

    assert donation.status == DonationStatus.pending
    assert donation.amount_kopecks == 10000
    assert donation.platform_fee_kopecks == 1500  # 15%
    assert donation.nco_amount_kopecks == 8500
    assert donation.campaign_id == campaign.id
    assert donation.user_id == user.id
    assert donation.payment_url is not None


async def test_create_donation_min_amount(db: AsyncSession, user: User, campaign: Campaign):
    """Amount below minimum raises MIN_DONATION_AMOUNT."""
    with pytest.raises(BusinessLogicError) as exc_info:
        await create_donation(db, campaign.id, 500, user_id=user.id)

    assert exc_info.value.code == "MIN_DONATION_AMOUNT"


async def test_create_donation_inactive_campaign(db: AsyncSession, user: User, foundation):
    """Donating to an inactive campaign raises CAMPAIGN_NOT_ACTIVE."""
    completed = await create_campaign(db, foundation, status=CampaignStatus.completed)

    with pytest.raises(BusinessLogicError) as exc_info:
        await create_donation(db, completed.id, 5000, user_id=user.id)

    assert exc_info.value.code == "CAMPAIGN_NOT_ACTIVE"


async def test_create_donation_guest_requires_auth(db: AsyncSession, campaign: Campaign):
    """Guest donation with unknown email raises AUTH_REQUIRED (OTP flow required)."""
    guest_email = f"guest-{uuid7().hex[:8]}@example.com"

    with pytest.raises(AppError) as exc_info:
        await create_donation(db, campaign.id, 2000, email=guest_email)

    assert exc_info.value.code == "AUTH_REQUIRED"
    assert exc_info.value.details.get("is_new") is True


async def test_create_donation_guest_existing_active(db: AsyncSession, campaign: Campaign):
    """Guest donation with existing active user email raises AUTH_REQUIRED."""
    existing = await create_user(db, email="taken@example.com")

    with pytest.raises(AppError) as exc_info:
        await create_donation(db, campaign.id, 2000, email="taken@example.com")

    assert exc_info.value.code == "AUTH_REQUIRED"


async def test_create_donation_guest_deactivated(db: AsyncSession, campaign: Campaign):
    """Guest donation with deactivated user email raises ACCOUNT_DEACTIVATED."""
    await create_user(db, email="dead@example.com", is_active=False)

    with pytest.raises(AppError) as exc_info:
        await create_donation(db, campaign.id, 2000, email="dead@example.com")

    assert exc_info.value.code == "ACCOUNT_DEACTIVATED"


async def test_create_donation_guest_no_email(db: AsyncSession, campaign: Campaign):
    """Guest donation without email raises EMAIL_REQUIRED."""
    with pytest.raises(AppError) as exc_info:
        await create_donation(db, campaign.id, 2000)

    assert exc_info.value.code == "EMAIL_REQUIRED"


# ---------------------------------------------------------------------------
# list_donations / get_donation
# ---------------------------------------------------------------------------


async def test_list_donations(db: AsyncSession, user: User, campaign: Campaign):
    """list_donations returns only the requesting user's donations."""
    from tests.conftest import create_donation as factory_donation

    other_user = await create_user(db, email="other@example.com")

    d1 = await factory_donation(db, user, campaign, amount_kopecks=1000)
    d2 = await factory_donation(db, user, campaign, amount_kopecks=2000)
    _d3 = await factory_donation(db, other_user, campaign, amount_kopecks=3000)

    result = await list_donations(db, user.id)

    ids = {str(d.id) for d in result["data"]}
    assert str(d1.id) in ids
    assert str(d2.id) in ids
    assert str(_d3.id) not in ids


async def test_get_donation_not_found(db: AsyncSession, user: User):
    """get_donation for a missing ID raises NotFoundError."""
    with pytest.raises(NotFoundError):
        await get_donation(db, uuid7(), user.id)
