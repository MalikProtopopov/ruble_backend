"""Tests for /api/v1/thanks/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models import CampaignDonor, ThanksContent
from app.models.base import ThanksContentType

pytestmark = pytest.mark.asyncio


# ---- GET /api/v1/thanks/unseen ----


async def test_unseen_thanks(client, db, user, donor_headers, campaign):
    # User must be a donor of the campaign
    cd = CampaignDonor(campaign_id=campaign.id, user_id=user.id)
    db.add(cd)
    await db.flush()

    thanks = ThanksContent(
        id=uuid7(),
        campaign_id=campaign.id,
        type=ThanksContentType.video,
        media_url="https://cdn.test/video.mp4",
        title="Thanks!",
    )
    db.add(thanks)
    await db.flush()

    resp = await client.get("/api/v1/thanks/unseen", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    # Response may be a list or a dict with "data" key depending on serialization
    data = body if isinstance(body, list) else body.get("data", body)
    assert len(data) == 1
    assert data[0]["campaign_title"] == campaign.title
    assert data[0]["type"] == "video"


async def test_unseen_thanks_empty(client, donor_headers):
    # No donations, no campaign_donors => no thanks
    resp = await client.get("/api/v1/thanks/unseen", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    data = body if isinstance(body, list) else body.get("data", body)
    assert len(data) == 0


async def test_unseen_thanks_unauthorized(client):
    resp = await client.get("/api/v1/thanks/unseen")
    assert resp.status_code == 401


# ---- GET /api/v1/thanks/{id} ----


async def test_get_thanks_detail(client, db, user, donor_headers, campaign):
    thanks = ThanksContent(
        id=uuid7(),
        campaign_id=campaign.id,
        type=ThanksContentType.video,
        media_url="https://cdn.test/video.mp4",
        title="Thank you!",
        description="We appreciate your support.",
    )
    db.add(thanks)
    await db.flush()

    resp = await client.get(
        f"/api/v1/thanks/{thanks.id}",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(thanks.id)
    assert body["campaign_title"] == campaign.title
    assert "user_contribution" in body
    assert "total_donated_kopecks" in body["user_contribution"]


async def test_get_thanks_not_found(client, donor_headers):
    fake_id = str(uuid7())
    resp = await client.get(
        f"/api/v1/thanks/{fake_id}",
        headers=donor_headers,
    )
    assert resp.status_code == 404
