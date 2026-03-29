"""Tests for /api/v1/transactions/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import TransactionStatus
from tests.conftest import create_subscription, create_transaction

pytestmark = pytest.mark.asyncio


# ---- GET /api/v1/transactions/ ----


async def test_list_transactions(client, db, user, donor_headers, foundation, campaign):
    sub = await create_subscription(db, user)
    await create_transaction(db, sub, campaign)
    await create_transaction(db, sub, campaign, status=TransactionStatus.failed)

    resp = await client.get("/api/v1/transactions", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert len(body["data"]) == 2


async def test_list_transactions_filter_status(client, db, user, donor_headers, foundation, campaign):
    sub = await create_subscription(db, user)
    await create_transaction(db, sub, campaign, status=TransactionStatus.success)
    await create_transaction(db, sub, campaign, status=TransactionStatus.failed)

    resp = await client.get(
        "/api/v1/transactions?status=success",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "success"


async def test_list_transactions_filter_date(client, db, user, donor_headers, foundation, campaign):
    sub = await create_subscription(db, user)
    await create_transaction(db, sub, campaign)

    # Use a future date_from to get zero results
    resp = await client.get(
        "/api/v1/transactions?date_from=2099-01-01T00:00:00Z",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 0


async def test_list_transactions_unauthorized(client):
    resp = await client.get("/api/v1/transactions")
    assert resp.status_code == 401


# ---- GET /api/v1/transactions/{id} ----


async def test_get_transaction(client, db, user, donor_headers, foundation, campaign):
    sub = await create_subscription(db, user)
    txn = await create_transaction(db, sub, campaign)

    resp = await client.get(
        f"/api/v1/transactions/{txn.id}",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(txn.id)
    assert body["amount_kopecks"] == txn.amount_kopecks
    assert "platform_fee_kopecks" in body
    assert "nco_amount_kopecks" in body


async def test_get_transaction_not_found(client, donor_headers):
    fake_id = str(uuid7())
    resp = await client.get(
        f"/api/v1/transactions/{fake_id}",
        headers=donor_headers,
    )
    assert resp.status_code == 404
