"""Tests for /api/v1/campaigns/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models import CampaignDocument
from app.models.base import CampaignStatus, FoundationStatus
from tests.conftest import create_campaign, create_foundation

pytestmark = pytest.mark.asyncio


# ---- GET /api/v1/campaigns/ ----


async def test_list_campaigns_success(client, campaign):
    resp = await client.get("/api/v1/campaigns")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert len(body["data"]) >= 1
    titles = [c["title"] for c in body["data"]]
    assert campaign.title in titles


async def test_list_campaigns_pagination(client, db, foundation):
    for i in range(25):
        await create_campaign(db, foundation, title=f"Campaign {i}")

    resp = await client.get("/api/v1/campaigns?limit=20")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 20
    assert body["pagination"]["has_more"] is True


async def test_list_campaigns_excludes_suspended_foundation(client, db):
    suspended = await create_foundation(db, name="Suspended Org", status=FoundationStatus.suspended)
    await create_campaign(db, suspended, title="Hidden Campaign")

    resp = await client.get("/api/v1/campaigns")
    assert resp.status_code == 200
    titles = [c["title"] for c in resp.json()["data"]]
    assert "Hidden Campaign" not in titles


async def test_list_campaigns_excludes_draft(client, db, foundation):
    await create_campaign(db, foundation, title="Draft Campaign", status=CampaignStatus.draft)

    resp = await client.get("/api/v1/campaigns")
    assert resp.status_code == 200
    titles = [c["title"] for c in resp.json()["data"]]
    assert "Draft Campaign" not in titles


# ---- GET /api/v1/campaigns/{id} ----


async def test_get_campaign_detail(client, db, campaign):
    resp = await client.get(f"/api/v1/campaigns/{str(campaign.id)}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(campaign.id)
    assert body["title"] == campaign.title
    assert "documents" in body
    assert "thanks_contents" in body
    assert "foundation" in body


async def test_get_campaign_not_found(client):
    fake_id = str(uuid7())
    resp = await client.get(f"/api/v1/campaigns/{fake_id}")
    assert resp.status_code == 404


async def test_get_campaign_completed_with_close_note(client, db, foundation):
    c = await create_campaign(db, foundation, title="Done Campaign", status=CampaignStatus.completed)
    c.closed_early = True
    c.close_note = "Goal reached early"
    await db.flush()

    resp = await client.get(f"/api/v1/campaigns/{str(c.id)}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["closed_early"] is True
    assert body["close_note"] == "Goal reached early"


# ---- GET /api/v1/campaigns/{id}/documents ----


async def test_get_documents(client, db, campaign):
    doc1 = CampaignDocument(
        id=uuid7(), campaign_id=campaign.id,
        title="Report", file_url="https://cdn.example.com/report.pdf", sort_order=1,
    )
    db.add(doc1)
    await db.flush()
    doc2 = CampaignDocument(
        id=uuid7(), campaign_id=campaign.id,
        title="Invoice", file_url="https://cdn.example.com/invoice.pdf", sort_order=0,
    )
    db.add(doc2)
    await db.flush()

    resp = await client.get(f"/api/v1/campaigns/{str(campaign.id)}/documents")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 2
    # Should be ordered by sort_order
    assert docs[0]["title"] == "Invoice"
    assert docs[1]["title"] == "Report"


# ---- GET /api/v1/campaigns/{id}/share ----


async def test_get_share(client, db, campaign, donor_headers):
    resp = await client.get(
        f"/api/v1/campaigns/{str(campaign.id)}/share",
        headers=donor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "share_url" in body
    assert "title" in body
    assert body["title"] == campaign.title


async def test_get_share_unauthorized(client, campaign):
    resp = await client.get(f"/api/v1/campaigns/{str(campaign.id)}/share")
    assert resp.status_code == 401
