"""Tests for /api/v1/admin/campaigns/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import CampaignStatus
from tests.conftest import create_campaign, create_foundation

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# GET /api/v1/admin/campaigns/
# ---------------------------------------------------------------------------


async def test_list_campaigns(client, db, admin_headers, foundation):
    await create_campaign(db, foundation, title="Camp A")
    await create_campaign(db, foundation, title="Camp B")
    resp = await client.get("/api/v1/admin/campaigns", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 2


async def test_list_campaigns_filter_status(client, db, admin_headers, foundation):
    await create_campaign(db, foundation, status=CampaignStatus.draft, title="Draft Camp")
    await create_campaign(db, foundation, status=CampaignStatus.active, title="Active Camp")
    resp = await client.get(
        "/api/v1/admin/campaigns",
        headers=admin_headers,
        params={"status": "draft"},
    )
    assert resp.status_code == 200
    body = resp.json()
    for item in body["data"]:
        assert item["status"] == "draft"


async def test_list_campaigns_filter_foundation(client, db, admin_headers):
    f1 = await create_foundation(db, name="Foundation X")
    f2 = await create_foundation(db, name="Foundation Y")
    await create_campaign(db, f1, title="Camp X")
    await create_campaign(db, f2, title="Camp Y")
    resp = await client.get(
        "/api/v1/admin/campaigns",
        headers=admin_headers,
        params={"foundation_id": str(f1.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    for item in body["data"]:
        assert item["foundation_id"] == str(f1.id)


async def test_list_campaigns_search(client, db, admin_headers, foundation):
    await create_campaign(db, foundation, title="UniqueSearchTitle")
    resp = await client.get(
        "/api/v1/admin/campaigns",
        headers=admin_headers,
        params={"search": "UniqueSearch"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    assert "UniqueSearchTitle" in body["data"][0]["title"]


# ---------------------------------------------------------------------------
# POST /api/v1/admin/campaigns/
# ---------------------------------------------------------------------------


async def test_create_campaign(client, db, admin_headers, foundation):
    resp = await client.post(
        "/api/v1/admin/campaigns",
        headers=admin_headers,
        json={
            "foundation_id": str(foundation.id),
            "title": "Brand New Campaign",
            "goal_amount": 500000,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Brand New Campaign"
    assert body["status"] == "draft"
    assert body["goal_amount"] == 500000


async def test_create_campaign_invalid_foundation(client, db, admin_headers):
    fake_id = str(uuid7())
    resp = await client.post(
        "/api/v1/admin/campaigns",
        headers=admin_headers,
        json={
            "foundation_id": fake_id,
            "title": "Orphan Campaign",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/admin/campaigns/{id}
# ---------------------------------------------------------------------------


async def test_get_campaign(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, title="Detail Campaign")
    resp = await client.get(
        f"/api/v1/admin/campaigns/{camp.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Detail Campaign"
    assert "documents" in body
    assert "thanks_contents" in body


# ---------------------------------------------------------------------------
# PATCH /api/v1/admin/campaigns/{id}
# ---------------------------------------------------------------------------


async def test_update_campaign(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, title="Old Title")
    resp = await client.patch(
        f"/api/v1/admin/campaigns/{camp.id}",
        headers=admin_headers,
        json={"title": "New Title"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "New Title"


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


async def test_publish_campaign(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.draft)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/publish",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


async def test_publish_invalid_transition(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.completed)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/publish",
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_pause_campaign(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.active)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/pause",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


async def test_complete_campaign(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.active)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/complete",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_archive_campaign(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.completed)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/archive",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


# ---------------------------------------------------------------------------
# POST .../close-early
# ---------------------------------------------------------------------------


async def test_close_early(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.active)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/close-early",
        headers=admin_headers,
        json={"close_note": "Сбор завершён досрочно"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["closed_early"] is True
    assert body["close_note"] == "Сбор завершён досрочно"
    assert body["status"] == "completed"


async def test_close_early_already_completed(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.completed)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/close-early",
        headers=admin_headers,
        json={"close_note": "Too late"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST .../force-realloc
# ---------------------------------------------------------------------------


async def test_force_realloc(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.active)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/force-realloc",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "reallocated_subscriptions" in body
    assert body["reallocated_subscriptions"] >= 0


# ---------------------------------------------------------------------------
# Offline payments
# ---------------------------------------------------------------------------


async def test_create_offline_payment(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.active, collected_amount=0)
    resp = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/offline-payment",
        headers=admin_headers,
        json={
            "amount_kopecks": 50000,
            "payment_method": "bank_transfer",
            "description": "Test payment",
            "payment_date": "2026-03-25",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount_kopecks"] == 50000
    assert body["payment_method"] == "bank_transfer"

    # Verify collected_amount increased
    await db.refresh(camp)
    assert camp.collected_amount == 50000


async def test_create_offline_payment_duplicate(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.active)
    payload = {
        "amount_kopecks": 10000,
        "payment_method": "bank_transfer",
        "description": "Dup test",
        "external_reference": "REF-001",
        "payment_date": "2026-03-25",
    }
    resp1 = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/offline-payment",
        headers=admin_headers,
        json=payload,
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/offline-payment",
        headers=admin_headers,
        json=payload,
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["details"]["code"] == "DUPLICATE_OFFLINE_PAYMENT"


async def test_list_offline_payments(client, db, admin_headers, foundation):
    camp = await create_campaign(db, foundation, status=CampaignStatus.active)
    # Create a payment first
    await client.post(
        f"/api/v1/admin/campaigns/{camp.id}/offline-payment",
        headers=admin_headers,
        json={
            "amount_kopecks": 20000,
            "payment_method": "cash",
            "payment_date": "2026-03-25",
        },
    )
    resp = await client.get(
        f"/api/v1/admin/campaigns/{camp.id}/offline-payments",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


async def test_create_document(client, db, admin_headers, campaign):
    resp = await client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/documents",
        headers=admin_headers,
        json={"title": "Report", "file_url": "https://cdn.test/doc.pdf"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Report"
    assert body["file_url"] == "https://cdn.test/doc.pdf"


async def test_delete_document(client, db, admin_headers, campaign):
    # Create document first
    create_resp = await client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/documents",
        headers=admin_headers,
        json={"title": "To Delete", "file_url": "https://cdn.test/del.pdf"},
    )
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/admin/campaigns/{campaign.id}/documents/{doc_id}",
        headers=admin_headers,
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Thanks content
# ---------------------------------------------------------------------------


async def test_create_thanks(client, db, admin_headers, campaign):
    resp = await client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/thanks",
        headers=admin_headers,
        json={
            "type": "video",
            "media_url": "https://cdn.test/video.mp4",
            "title": "Thank you!",
            "description": "We appreciate your help",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "video"
    assert body["title"] == "Thank you!"


async def test_update_thanks(client, db, admin_headers, campaign):
    # Create thanks first
    create_resp = await client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/thanks",
        headers=admin_headers,
        json={
            "type": "video",
            "media_url": "https://cdn.test/vid.mp4",
            "title": "Original",
        },
    )
    assert create_resp.status_code == 201
    thanks_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/campaigns/{campaign.id}/thanks/{thanks_id}",
        headers=admin_headers,
        json={"title": "Updated Title"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


async def test_delete_thanks(client, db, admin_headers, campaign):
    # Create thanks first
    create_resp = await client.post(
        f"/api/v1/admin/campaigns/{campaign.id}/thanks",
        headers=admin_headers,
        json={
            "type": "audio",
            "media_url": "https://cdn.test/audio.mp3",
        },
    )
    assert create_resp.status_code == 201
    thanks_id = create_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/admin/campaigns/{campaign.id}/thanks/{thanks_id}",
        headers=admin_headers,
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Unauthorized access
# ---------------------------------------------------------------------------


async def test_list_campaigns_unauthorized(client, db):
    resp = await client.get("/api/v1/admin/campaigns")
    assert resp.status_code in (401, 403)
