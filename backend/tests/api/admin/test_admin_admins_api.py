"""Tests for /api/v1/admin/admins/ endpoints."""

import pytest
from app.models.base import uuid7

from tests.conftest import create_admin

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/admins"


# ---- GET /api/v1/admin/admins/ ----


async def test_list_admins(client, db, admin_headers):
    resp = await client.get(BASE, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert len(body["data"]) >= 1


# ---- POST /api/v1/admin/admins/ ----


async def test_create_admin(client, db, admin_headers):
    resp = await client.post(
        BASE,
        headers=admin_headers,
        json={
            "email": "new-admin@test.com",
            "password": "SecurePass123",
            "name": "New Admin",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "new-admin@test.com"
    assert body["name"] == "New Admin"
    assert body["is_active"] is True


async def test_create_admin_duplicate_email(client, db, admin_headers):
    await create_admin(db, email="dup-admin@test.com")
    resp = await client.post(
        BASE,
        headers=admin_headers,
        json={
            "email": "dup-admin@test.com",
            "password": "SecurePass123",
            "name": "Duplicate",
        },
    )
    assert resp.status_code == 409


# ---- GET /api/v1/admin/admins/{id} ----


async def test_get_admin(client, db, admin, admin_headers):
    resp = await client.get(f"{BASE}/{admin.id}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(admin.id)
    assert body["email"] == admin.email


# ---- PATCH /api/v1/admin/admins/{id} ----


async def test_update_admin(client, db, admin_headers):
    target = await create_admin(db, email="update-me@test.com", name="Old Name")
    resp = await client.patch(
        f"{BASE}/{target.id}",
        headers=admin_headers,
        json={"name": "New Name"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "New Name"


# ---- POST /api/v1/admin/admins/{id}/deactivate ----


async def test_deactivate_admin(client, db, admin_headers):
    target = await create_admin(db, email="deact-target@test.com")
    resp = await client.post(f"{BASE}/{target.id}/deactivate", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is False


async def test_deactivate_self(client, db, admin, admin_headers):
    resp = await client.post(f"{BASE}/{admin.id}/deactivate", headers=admin_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


# ---- POST /api/v1/admin/admins/{id}/activate ----


async def test_activate_admin(client, db, admin_headers):
    target = await create_admin(db, email="activate-target@test.com", is_active=False)
    resp = await client.post(f"{BASE}/{target.id}/activate", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is True
