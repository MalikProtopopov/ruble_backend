"""Tests for /api/v1/patron/payment-links/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import CampaignStatus
from tests.conftest import create_campaign, create_foundation

pytestmark = pytest.mark.asyncio


# ---- POST /api/v1/patron/payment-links/ ----


async def test_create_payment_link(client, db, patron_user, patron_headers, campaign):
    resp = await client.post("/api/v1/patron/payment-links", headers=patron_headers, json={
        "campaign_id": str(campaign.id),
        "amount_kopecks": 10000,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert "payment_url" in body
    assert body["amount_kopecks"] == 10000
    assert body["campaign_id"] == str(campaign.id)


async def test_create_payment_link_not_patron(client, donor_headers, campaign):
    resp = await client.post("/api/v1/patron/payment-links", headers=donor_headers, json={
        "campaign_id": str(campaign.id),
        "amount_kopecks": 10000,
    })
    assert resp.status_code == 403


async def test_create_payment_link_inactive_campaign(client, db, patron_user, patron_headers):
    foundation = await create_foundation(db)
    inactive = await create_campaign(db, foundation, status=CampaignStatus.paused)

    resp = await client.post("/api/v1/patron/payment-links", headers=patron_headers, json={
        "campaign_id": str(inactive.id),
        "amount_kopecks": 10000,
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CAMPAIGN_NOT_ACTIVE"


async def test_create_payment_link_unauthorized(client, campaign):
    resp = await client.post("/api/v1/patron/payment-links", json={
        "campaign_id": str(campaign.id),
        "amount_kopecks": 10000,
    })
    assert resp.status_code == 401


# ---- GET /api/v1/patron/payment-links/ ----


async def test_list_payment_links(client, db, patron_user, patron_headers, campaign):
    # Create a link first
    await client.post("/api/v1/patron/payment-links", headers=patron_headers, json={
        "campaign_id": str(campaign.id),
        "amount_kopecks": 5000,
    })

    resp = await client.get("/api/v1/patron/payment-links", headers=patron_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert len(body["data"]) >= 1


# ---- GET /api/v1/patron/payment-links/{id} ----


async def test_get_payment_link(client, db, patron_user, patron_headers, campaign):
    # Create a link first
    create_resp = await client.post("/api/v1/patron/payment-links", headers=patron_headers, json={
        "campaign_id": str(campaign.id),
        "amount_kopecks": 7500,
    })
    link_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/patron/payment-links/{link_id}",
        headers=patron_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == link_id
    assert body["amount_kopecks"] == 7500
