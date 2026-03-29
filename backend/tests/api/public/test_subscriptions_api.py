"""Tests for /api/v1/subscriptions/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import CampaignStatus, SubscriptionStatus
from tests.conftest import create_campaign, create_foundation, create_subscription

pytestmark = pytest.mark.asyncio


# ---- POST /api/v1/subscriptions/ ----


async def test_create_subscription_success(client, db, user, donor_headers, campaign):
    resp = await client.post("/api/v1/subscriptions", headers=donor_headers, json={
        "amount_kopecks": 300,
        "billing_period": "monthly",
        "allocation_strategy": "platform_pool",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending_payment_method"
    assert body["amount_kopecks"] == 300
    assert body["billing_period"] == "monthly"
    assert body["allocation_strategy"] == "platform_pool"


async def test_create_subscription_invalid_amount(client, donor_headers):
    resp = await client.post("/api/v1/subscriptions", headers=donor_headers, json={
        "amount_kopecks": 200,
        "billing_period": "monthly",
        "allocation_strategy": "platform_pool",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_AMOUNT"


async def test_create_subscription_limit(client, db, user, donor_headers):
    for _ in range(5):
        await create_subscription(db, user)
    resp = await client.post("/api/v1/subscriptions", headers=donor_headers, json={
        "amount_kopecks": 100,
        "billing_period": "weekly",
        "allocation_strategy": "platform_pool",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SUBSCRIPTION_LIMIT_EXCEEDED"


async def test_create_subscription_specific_campaign(client, db, user, donor_headers, campaign):
    resp = await client.post("/api/v1/subscriptions", headers=donor_headers, json={
        "amount_kopecks": 500,
        "billing_period": "monthly",
        "allocation_strategy": "specific_campaign",
        "campaign_id": str(campaign.id),
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["campaign_id"] == str(campaign.id)
    assert body["allocation_strategy"] == "specific_campaign"


async def test_create_subscription_unauthorized(client):
    resp = await client.post("/api/v1/subscriptions", json={
        "amount_kopecks": 300,
        "billing_period": "monthly",
        "allocation_strategy": "platform_pool",
    })
    assert resp.status_code == 401


# ---- GET /api/v1/subscriptions/ ----


async def test_list_subscriptions(client, db, user, donor_headers):
    await create_subscription(db, user, status=SubscriptionStatus.active)
    await create_subscription(db, user, status=SubscriptionStatus.paused)
    await create_subscription(db, user, status=SubscriptionStatus.cancelled)

    resp = await client.get("/api/v1/subscriptions", headers=donor_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Should include active and paused but not cancelled
    assert len(data) == 2
    statuses = {s["status"] for s in data}
    assert "cancelled" not in statuses


async def test_list_subscriptions_empty(client, donor_headers):
    resp = await client.get("/api/v1/subscriptions", headers=donor_headers)
    assert resp.status_code == 200
    assert resp.json() == []


# ---- PATCH /api/v1/subscriptions/{id} ----


async def test_update_subscription(client, db, user, donor_headers):
    sub = await create_subscription(db, user, amount_kopecks=300)
    resp = await client.patch(
        f"/api/v1/subscriptions/{sub.id}",
        headers=donor_headers,
        json={"amount_kopecks": 500},
    )
    assert resp.status_code == 200
    assert resp.json()["amount_kopecks"] == 500


async def test_update_subscription_not_found(client, donor_headers):
    fake_id = str(uuid7())
    resp = await client.patch(
        f"/api/v1/subscriptions/{fake_id}",
        headers=donor_headers,
        json={"amount_kopecks": 500},
    )
    assert resp.status_code == 404


# ---- POST /api/v1/subscriptions/{id}/pause ----


async def test_pause_subscription(client, db, user, donor_headers):
    sub = await create_subscription(db, user, status=SubscriptionStatus.active)
    resp = await client.post(
        f"/api/v1/subscriptions/{sub.id}/pause",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


async def test_pause_not_active(client, db, user, donor_headers):
    sub = await create_subscription(db, user, status=SubscriptionStatus.paused)
    resp = await client.post(
        f"/api/v1/subscriptions/{sub.id}/pause",
        headers=donor_headers,
    )
    assert resp.status_code == 422


# ---- POST /api/v1/subscriptions/{id}/resume ----


async def test_resume_subscription(client, db, user, donor_headers):
    sub = await create_subscription(db, user, status=SubscriptionStatus.paused)
    resp = await client.post(
        f"/api/v1/subscriptions/{sub.id}/resume",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


# ---- DELETE /api/v1/subscriptions/{id} ----


async def test_cancel_subscription(client, db, user, donor_headers):
    sub = await create_subscription(db, user, status=SubscriptionStatus.active)
    resp = await client.delete(
        f"/api/v1/subscriptions/{sub.id}",
        headers=donor_headers,
    )
    assert resp.status_code == 204


# ---- POST /api/v1/subscriptions/{id}/bind-card ----


async def test_bind_card(client, db, user, donor_headers):
    sub = await create_subscription(
        db, user, status=SubscriptionStatus.pending_payment_method,
    )
    resp = await client.post(
        f"/api/v1/subscriptions/{sub.id}/bind-card",
        headers=donor_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "payment_url" in body
    assert body["subscription_id"] == str(sub.id)
    # amount = daily amount * period multiplier (monthly=30)
    assert body["amount_kopecks"] == sub.amount_kopecks * 30


async def test_bind_card_already_active(client, db, user, donor_headers):
    sub = await create_subscription(db, user, status=SubscriptionStatus.active)
    resp = await client.post(
        f"/api/v1/subscriptions/{sub.id}/bind-card",
        headers=donor_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "SUBSCRIPTION_ALREADY_ACTIVE"
