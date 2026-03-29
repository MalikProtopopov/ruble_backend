"""Tests for /api/v1/admin/stats/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import DonationStatus
from tests.conftest import create_donation, create_subscription

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/stats"


# ---- GET /api/v1/admin/stats/overview ----


async def test_stats_overview(client, db, admin_headers, user, foundation, campaign):
    donation = await create_donation(
        db, user, campaign, amount_kopecks=50000, status=DonationStatus.success
    )
    sub = await create_subscription(db, user)

    resp = await client.get(f"{BASE}/overview", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "gmv_kopecks" in body
    assert "active_subscriptions" in body
    assert "total_donors" in body
    assert "platform_fee_kopecks" in body
    assert body["gmv_kopecks"] >= 50000
    assert body["active_subscriptions"] >= 1
    assert body["total_donors"] >= 1


async def test_stats_overview_with_period(client, db, admin_headers, user, foundation, campaign):
    await create_donation(db, user, campaign, amount_kopecks=30000, status=DonationStatus.success)

    resp = await client.get(
        f"{BASE}/overview",
        headers=admin_headers,
        params={"period_from": "2026-01-01", "period_to": "2026-12-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "gmv_kopecks" in body
    assert "new_donors_period" in body


# ---- GET /api/v1/admin/stats/campaigns/{id} ----


async def test_campaign_stats(client, db, admin_headers, user, foundation, campaign):
    await create_donation(db, user, campaign, amount_kopecks=25000, status=DonationStatus.success)

    resp = await client.get(f"{BASE}/campaigns/{campaign.id}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["campaign_id"] == str(campaign.id)
    assert body["title"] == campaign.title
    assert body["donations_count"] >= 1
    assert body["donations_amount_kopecks"] >= 25000


async def test_campaign_stats_not_found(client, db, admin_headers):
    fake_id = uuid7()
    resp = await client.get(f"{BASE}/campaigns/{fake_id}", headers=admin_headers)
    assert resp.status_code == 404
