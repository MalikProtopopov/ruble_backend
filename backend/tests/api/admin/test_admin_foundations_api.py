"""Tests for /api/v1/admin/foundations/ endpoints."""

import pytest
from app.models.base import uuid7

from tests.conftest import create_foundation

pytestmark = pytest.mark.asyncio


# ---- GET /api/v1/admin/foundations/ ----


async def test_list_foundations(client, db, admin_headers):
    await create_foundation(db, name="Alpha Foundation")
    await create_foundation(db, name="Beta Foundation")
    resp = await client.get("/api/v1/admin/foundations", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 2


async def test_list_foundations_filter_status(client, db, admin_headers):
    from app.models.base import FoundationStatus

    await create_foundation(db, name="Active One", status=FoundationStatus.active)
    await create_foundation(db, name="Pending One", status=FoundationStatus.pending_verification)
    resp = await client.get(
        "/api/v1/admin/foundations",
        headers=admin_headers,
        params={"status": "active"},
    )
    assert resp.status_code == 200
    body = resp.json()
    for item in body["data"]:
        assert item["status"] == "active"


async def test_list_foundations_search(client, db, admin_headers):
    await create_foundation(db, name="UniqueSearchableName")
    resp = await client.get(
        "/api/v1/admin/foundations",
        headers=admin_headers,
        params={"search": "UniqueSearchable"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    assert "UniqueSearchableName" in body["data"][0]["name"]


async def test_list_foundations_unauthorized(client, db):
    resp = await client.get("/api/v1/admin/foundations")
    assert resp.status_code in (401, 403)


# ---- POST /api/v1/admin/foundations/ ----


async def test_create_foundation(client, db, admin_headers):
    resp = await client.post(
        "/api/v1/admin/foundations",
        headers=admin_headers,
        json={
            "name": "New Foundation",
            "legal_name": 'OOO "New Foundation"',
            "inn": "123456789012",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "New Foundation"
    assert body["status"] == "pending_verification"


async def test_create_foundation_duplicate_inn(client, db, admin_headers):
    await create_foundation(db, inn="999888777666")
    resp = await client.post(
        "/api/v1/admin/foundations",
        headers=admin_headers,
        json={
            "name": "Another Foundation",
            "legal_name": 'OOO "Another"',
            "inn": "999888777666",
        },
    )
    assert resp.status_code == 409


# ---- GET /api/v1/admin/foundations/{id} ----


async def test_get_foundation(client, db, admin_headers):
    f = await create_foundation(db, name="Detail Foundation", inn="111222333444")
    resp = await client.get(
        f"/api/v1/admin/foundations/{f.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Detail Foundation"
    assert body["inn"] == "111222333444"
    assert "legal_name" in body


# ---- PATCH /api/v1/admin/foundations/{id} ----


async def test_update_foundation(client, db, admin_headers):
    f = await create_foundation(db, name="Old Name")
    resp = await client.patch(
        f"/api/v1/admin/foundations/{f.id}",
        headers=admin_headers,
        json={"name": "Updated Name"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated Name"


async def test_update_foundation_status_active(client, db, admin_headers):
    from app.models.base import FoundationStatus

    f = await create_foundation(db, status=FoundationStatus.pending_verification)
    assert f.verified_at is None
    resp = await client.patch(
        f"/api/v1/admin/foundations/{f.id}",
        headers=admin_headers,
        json={"status": "active"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["verified_at"] is not None
