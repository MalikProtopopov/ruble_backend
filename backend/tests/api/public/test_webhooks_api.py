"""Tests for /api/v1/webhooks/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import DonationStatus, TransactionStatus
from tests.conftest import create_donation, create_subscription, create_transaction

pytestmark = pytest.mark.asyncio


# ---- POST /api/v1/webhooks/yookassa ----


async def test_webhook_payment_succeeded(client, db, user, foundation, campaign):
    donation = await create_donation(db, user, campaign, status=DonationStatus.pending)
    donation.provider_payment_id = "pay_test_123"
    await db.flush()

    resp = await client.post("/api/v1/webhooks/yookassa", json={
        "event": "payment.succeeded",
        "object": {
            "id": "pay_test_123",
            "metadata": {"type": "donation", "entity_id": str(donation.id)},
        },
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    await db.refresh(donation)
    assert donation.status == DonationStatus.success


async def test_webhook_payment_canceled(client, db, user, foundation, campaign):
    donation = await create_donation(db, user, campaign, status=DonationStatus.pending)
    donation.provider_payment_id = "pay_cancel_456"
    await db.flush()

    resp = await client.post("/api/v1/webhooks/yookassa", json={
        "event": "payment.canceled",
        "object": {
            "id": "pay_cancel_456",
            "cancellation_details": {"reason": "card_expired"},
            "metadata": {"type": "donation", "entity_id": str(donation.id)},
        },
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    await db.refresh(donation)
    assert donation.status == DonationStatus.failed


async def test_webhook_unknown_event(client):
    resp = await client.post("/api/v1/webhooks/yookassa", json={
        "event": "refund.succeeded",
        "object": {"id": "ref_789"},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


async def test_webhook_empty_body(client):
    resp = await client.post("/api/v1/webhooks/yookassa", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
