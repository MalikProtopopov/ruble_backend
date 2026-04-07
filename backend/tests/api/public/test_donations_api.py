"""Tests for /api/v1/donations/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import CampaignStatus, DonationStatus
from tests.conftest import (
    create_campaign,
    create_donation,
    create_foundation,
    create_user,
)

pytestmark = pytest.mark.asyncio


# ---- POST /api/v1/donations/ ----


async def test_create_donation_authorized(client, db, donor_headers, campaign):
    resp = await client.post(
        "/api/v1/donations",
        json={
            "campaign_id": str(campaign.id),
            "amount_kopecks": 5000,
        },
        headers=donor_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["payment_url"] is not None
    assert body["campaign_id"] == str(campaign.id)
    assert body["amount_kopecks"] == 5000


async def test_create_donation_unauthenticated_requires_auth(client, db, campaign):
    """Donations always require an access token. Guests must call /auth/device-register first."""
    resp = await client.post(
        "/api/v1/donations",
        json={
            "campaign_id": str(campaign.id),
            "amount_kopecks": 5000,
        },
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "AUTH_REQUIRED"


async def test_create_donation_min_amount(client, db, donor_headers, campaign):
    resp = await client.post(
        "/api/v1/donations",
        json={
            "campaign_id": str(campaign.id),
            "amount_kopecks": 100,
        },
        headers=donor_headers,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "MIN_DONATION_AMOUNT"


async def test_create_donation_inactive_campaign(client, db, donor_headers, foundation):
    c = await create_campaign(db, foundation, status=CampaignStatus.completed)
    resp = await client.post(
        "/api/v1/donations",
        json={
            "campaign_id": str(c.id),
            "amount_kopecks": 5000,
        },
        headers=donor_headers,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "CAMPAIGN_NOT_ACTIVE"


async def test_create_donation_campaign_not_found(client, db, donor_headers):
    fake_id = str(uuid7())
    resp = await client.post(
        "/api/v1/donations",
        json={
            "campaign_id": fake_id,
            "amount_kopecks": 5000,
        },
        headers=donor_headers,
    )
    assert resp.status_code == 404


# ---- GET /api/v1/donations/ ----


async def test_list_donations(client, db, user, donor_headers, campaign):
    await create_donation(db, user, campaign, amount_kopecks=10000)
    await create_donation(db, user, campaign, amount_kopecks=20000)

    resp = await client.get("/api/v1/donations", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert len(body["data"]) >= 2


async def test_list_donations_filter_status(client, db, user, donor_headers, campaign):
    await create_donation(db, user, campaign, status=DonationStatus.success)
    await create_donation(db, user, campaign, status=DonationStatus.pending)

    resp = await client.get(
        "/api/v1/donations?status=success",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    for d in body["data"]:
        assert d["status"] == "success"


# ---- GET /api/v1/donations/{id} ----


async def test_get_donation_detail(client, db, user, donor_headers, campaign):
    donation = await create_donation(db, user, campaign)

    resp = await client.get(
        f"/api/v1/donations/{str(donation.id)}",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(donation.id)
    assert body["amount_kopecks"] == donation.amount_kopecks


async def test_get_donation_not_found(client, donor_headers):
    fake_id = str(uuid7())
    resp = await client.get(
        f"/api/v1/donations/{fake_id}",
        headers=donor_headers,
    )
    assert resp.status_code == 404


async def test_get_donation_unauthorized(client, db, user, campaign):
    donation = await create_donation(db, user, campaign)
    resp = await client.get(f"/api/v1/donations/{str(donation.id)}")
    assert resp.status_code == 401
