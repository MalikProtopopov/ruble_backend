"""Tests for the server-computed cooldown helper fields on campaign endpoints.

The mobile app must NOT compute time deltas locally — these fields exist so the
client never has to parse `next_available_at` or use the device clock.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update as sa_update

from app.core.config import settings
from app.models import Donation
from tests.conftest import (
    auth_header,
    create_campaign,
    create_donation,
    create_foundation,
    _make_access_token,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# /campaigns/{id} (detail)
# ---------------------------------------------------------------------------


async def test_detail_can_donate_now_true_when_no_donation(client, db, user):
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    headers = auth_header(_make_access_token(user.id, "donor"))

    resp = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["can_donate_now"] is True
    assert body["next_available_in_seconds"] is None
    assert body["next_available_at"] is None
    assert body["server_time_utc"] is not None


async def test_detail_can_donate_now_false_when_cooldown_active(client, db, user):
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    # Donation 1 hour ago — cooldown is 8 hours by default
    donation = await create_donation(db, user, campaign)
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.execute(
        sa_update(Donation).where(Donation.id == donation.id).values(created_at=one_hour_ago)
    )
    await db.flush()

    headers = auth_header(_make_access_token(user.id, "donor"))
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=headers)
    body = resp.json()

    assert body["can_donate_now"] is False
    assert body["next_available_in_seconds"] is not None
    # Cooldown 8h, donation 1h ago → about 7h = 25200 seconds remaining
    expected = (settings.DONATION_COOLDOWN_HOURS - 1) * 3600
    assert abs(body["next_available_in_seconds"] - expected) < 60  # ±1 min slack
    assert body["next_available_at"] is not None
    assert body["server_time_utc"] is not None


async def test_detail_can_donate_now_true_after_cooldown_expired(client, db, user):
    """Old donation outside cooldown window — user can donate again."""
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    donation = await create_donation(db, user, campaign)
    # Way before the cooldown window
    long_ago = datetime.now(timezone.utc) - timedelta(
        hours=settings.DONATION_COOLDOWN_HOURS + 5
    )
    await db.execute(
        sa_update(Donation).where(Donation.id == donation.id).values(created_at=long_ago)
    )
    await db.flush()

    headers = auth_header(_make_access_token(user.id, "donor"))
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=headers)
    body = resp.json()

    assert body["can_donate_now"] is True
    assert body["next_available_in_seconds"] is None
    # has_any_donation should still be True — past donations are remembered
    assert body["has_any_donation"] is True


async def test_detail_unauthenticated_has_null_helpers(client, db):
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}")
    body = resp.json()
    assert body["can_donate_now"] is None
    assert body["next_available_in_seconds"] is None
    assert body["server_time_utc"] is None


# ---------------------------------------------------------------------------
# /campaigns (list)
# ---------------------------------------------------------------------------


async def test_list_includes_cooldown_helpers_for_authenticated(client, db, user):
    foundation = await create_foundation(db)
    c1 = await create_campaign(db, foundation, title="Fresh")
    c2 = await create_campaign(db, foundation, title="On cooldown")

    # c1 — no donation, can donate now
    # c2 — donation 2h ago, cannot donate now
    donation = await create_donation(db, user, c2)
    await db.execute(
        sa_update(Donation)
        .where(Donation.id == donation.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(hours=2))
    )
    await db.flush()

    headers = auth_header(_make_access_token(user.id, "donor"))
    resp = await client.get("/api/v1/campaigns", headers=headers)
    items = {item["title"]: item for item in resp.json()["data"]}

    fresh = items["Fresh"]
    assert fresh["can_donate_now"] is True
    assert fresh["next_available_in_seconds"] is None

    cooled = items["On cooldown"]
    assert cooled["can_donate_now"] is False
    assert cooled["next_available_in_seconds"] is not None
    assert cooled["next_available_in_seconds"] > 0
    assert cooled["server_time_utc"] is not None


async def test_list_unauthenticated_has_null_helpers(client, db):
    foundation = await create_foundation(db)
    await create_campaign(db, foundation)
    resp = await client.get("/api/v1/campaigns")
    items = resp.json()["data"]
    assert items
    item = items[0]
    assert item["can_donate_now"] is None
    assert item["next_available_in_seconds"] is None


# ---------------------------------------------------------------------------
# Donation cooldown 429 — also exposes the new field name
# ---------------------------------------------------------------------------


async def test_donation_cooldown_response_includes_seconds_field(client, db, user):
    """The 429 response from POST /donations must expose next_available_in_seconds."""
    from app.models.base import uuid7

    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    # Pre-existing successful donation 1h ago — triggers cooldown
    donation = await create_donation(db, user, campaign)
    await db.execute(
        sa_update(Donation)
        .where(Donation.id == donation.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(hours=1))
    )
    await db.flush()

    headers = auth_header(_make_access_token(user.id, "donor"))
    resp = await client.post(
        "/api/v1/donations",
        headers=headers,
        json={"campaign_id": str(campaign.id), "amount_kopecks": 1000},
    )
    assert resp.status_code == 429
    details = resp.json()["error"]["details"]
    assert "next_available_in_seconds" in details
    assert "retry_after" in details  # legacy alias still present
    assert details["next_available_in_seconds"] == details["retry_after"]
    assert "server_time_utc" in details
    assert details["next_available_in_seconds"] > 0
