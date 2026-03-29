"""Tests for /api/v1/me/ endpoints."""

import pytest

pytestmark = pytest.mark.asyncio


# ---- GET /api/v1/me/ ----


async def test_get_profile(client, donor_headers, user):
    resp = await client.get("/api/v1/me", headers=donor_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == user.email
    assert "name" in body
    assert "role" in body
    assert "notification_preferences" in body
    assert "timezone" in body


async def test_get_profile_unauthorized(client):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


# ---- PATCH /api/v1/me/ ----


async def test_update_profile_name(client, donor_headers):
    resp = await client.patch(
        "/api/v1/me",
        json={"name": "New Name"},
        headers=donor_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


async def test_update_profile_timezone(client, donor_headers):
    resp = await client.patch(
        "/api/v1/me",
        json={"timezone": "Asia/Tokyo"},
        headers=donor_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["timezone"] == "Asia/Tokyo"


# ---- PATCH /api/v1/me/notifications ----


async def test_update_notifications(client, donor_headers):
    resp = await client.patch(
        "/api/v1/me/notifications",
        json={"push_on_payment": False},
        headers=donor_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["push_on_payment"] is False


async def test_update_notifications_unauthorized(client):
    resp = await client.patch(
        "/api/v1/me/notifications",
        json={"push_on_payment": False},
    )
    assert resp.status_code == 401


# ---- DELETE /api/v1/me/ ----


async def test_delete_account(client, donor_headers):
    resp = await client.delete("/api/v1/me", headers=donor_headers)
    assert resp.status_code == 204


async def test_delete_account_unauthorized(client):
    resp = await client.delete("/api/v1/me")
    assert resp.status_code == 401
