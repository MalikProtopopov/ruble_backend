"""Tests for /api/v1/admin/payouts/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import DonationStatus
from tests.conftest import create_donation, create_foundation

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/payouts"


# ---- GET /api/v1/admin/payouts/ ----


async def test_list_payouts(client, db, admin_headers):
    resp = await client.get(BASE, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert isinstance(body["data"], list)


async def test_list_payouts_filter(client, db, admin_headers, foundation):
    resp = await client.get(
        BASE, headers=admin_headers, params={"foundation_id": str(foundation.id)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body


# ---- POST /api/v1/admin/payouts/ ----


async def test_create_payout(client, db, admin_headers, foundation):
    resp = await client.post(
        BASE,
        headers=admin_headers,
        json={
            "foundation_id": str(foundation.id),
            "amount_kopecks": 100000,
            "period_from": "2026-03-01",
            "period_to": "2026-03-31",
            "transfer_reference": "PP-001",
            "note": "Monthly payout",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount_kopecks"] == 100000
    assert body["foundation_id"] == str(foundation.id)
    assert body["transfer_reference"] == "PP-001"


async def test_create_payout_invalid_foundation(client, db, admin_headers):
    fake_id = uuid7()
    resp = await client.post(
        BASE,
        headers=admin_headers,
        json={
            "foundation_id": str(fake_id),
            "amount_kopecks": 50000,
            "period_from": "2026-03-01",
            "period_to": "2026-03-31",
        },
    )
    assert resp.status_code == 404


# ---- GET /api/v1/admin/payouts/balance ----


async def test_get_balance(client, db, admin_headers, foundation):
    resp = await client.get(f"{BASE}/balance", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "balances" in body
    assert isinstance(body["balances"], list)


async def test_get_balance_with_data(client, db, admin_headers, user, foundation, campaign):
    # Create a donation so the foundation has incoming funds
    await create_donation(
        db, user, campaign, amount_kopecks=100000, status=DonationStatus.success
    )

    # Create a payout for part of the balance
    payout_resp = await client.post(
        BASE,
        headers=admin_headers,
        json={
            "foundation_id": str(foundation.id),
            "amount_kopecks": 30000,
            "period_from": "2026-03-01",
            "period_to": "2026-03-31",
        },
    )
    assert payout_resp.status_code == 201

    resp = await client.get(f"{BASE}/balance", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["balances"]) >= 1
    foundation_balance = next(
        b for b in body["balances"] if b["foundation_id"] == str(foundation.id)
    )
    assert foundation_balance["total_paid_kopecks"] >= 30000
    assert foundation_balance["total_nco_kopecks"] > 0
