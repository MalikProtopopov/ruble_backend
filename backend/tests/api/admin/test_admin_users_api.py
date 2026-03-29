"""Tests for /api/v1/admin/users/ endpoints."""

import pytest
from app.models.base import uuid7

from app.models.base import DonationStatus, UserRole
from tests.conftest import (
    auth_header,
    create_donation,
    create_subscription,
    create_user,
)

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/admin/users"


# ---- GET /api/v1/admin/users/ ----


async def test_list_users(client, db, admin_headers, user):
    resp = await client.get(BASE, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    emails = [u["email"] for u in body["data"]]
    assert user.email in emails


async def test_list_users_filter_role(client, db, admin_headers, user, patron_user):
    resp = await client.get(BASE, headers=admin_headers, params={"role": "patron"})
    assert resp.status_code == 200
    body = resp.json()
    emails = [u["email"] for u in body["data"]]
    assert patron_user.email in emails
    assert user.email not in emails


async def test_list_users_search(client, db, admin_headers, user):
    resp = await client.get(BASE, headers=admin_headers, params={"search": user.email})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    assert body["data"][0]["email"] == user.email


async def test_list_users_unauthorized(client, db, donor_headers):
    resp = await client.get(BASE, headers=donor_headers)
    assert resp.status_code in (401, 403)


# ---- GET /api/v1/admin/users/{id} ----


async def test_get_user_detail(client, db, admin_headers, user, foundation, campaign):
    sub = await create_subscription(db, user)
    donation = await create_donation(db, user, campaign)

    resp = await client.get(f"{BASE}/{user.id}", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == user.email
    assert len(body["subscriptions"]) >= 1
    assert len(body["recent_donations"]) >= 1


# ---- POST /api/v1/admin/users/{id}/grant-patron ----


async def test_grant_patron(client, db, admin_headers, user):
    resp = await client.post(f"{BASE}/{user.id}/grant-patron", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "patron"


async def test_grant_patron_not_found(client, db, admin_headers):
    fake_id = uuid7()
    resp = await client.post(f"{BASE}/{fake_id}/grant-patron", headers=admin_headers)
    assert resp.status_code == 404


# ---- POST /api/v1/admin/users/{id}/revoke-patron ----


async def test_revoke_patron(client, db, admin_headers, patron_user):
    resp = await client.post(f"{BASE}/{patron_user.id}/revoke-patron", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "donor"


# ---- POST /api/v1/admin/users/{id}/deactivate ----


async def test_deactivate_user(client, db, admin_headers, user):
    resp = await client.post(f"{BASE}/{user.id}/deactivate", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is False


# ---- POST /api/v1/admin/users/{id}/activate ----


async def test_activate_user(client, db, admin_headers):
    inactive = await create_user(db, is_active=False)
    resp = await client.post(f"{BASE}/{inactive.id}/activate", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is True
