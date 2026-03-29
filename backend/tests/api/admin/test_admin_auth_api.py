"""Tests for /api/v1/admin/auth/ endpoints."""

import hashlib

import pytest
from app.models.base import uuid7

from tests.conftest import create_admin, create_refresh_token_record

pytestmark = pytest.mark.asyncio


# ---- POST /api/v1/admin/auth/login ----


async def test_admin_login_success(client, db):
    admin = await create_admin(db, email="admin@test.com", password="Secret123")
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin@test.com", "password": "Secret123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["admin"]["email"] == "admin@test.com"
    assert body["admin"]["name"] == "Test Admin"


async def test_admin_login_wrong_password(client, db):
    await create_admin(db, email="admin-wp@test.com", password="Correct123")
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "admin-wp@test.com", "password": "WrongPassword"},
    )
    assert resp.status_code == 401


async def test_admin_login_nonexistent(client, db):
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "nobody@test.com", "password": "Whatever123"},
    )
    assert resp.status_code == 401


async def test_admin_login_deactivated(client, db):
    await create_admin(db, email="deactivated@test.com", password="Secret123", is_active=False)
    resp = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "deactivated@test.com", "password": "Secret123"},
    )
    assert resp.status_code == 401


# ---- POST /api/v1/admin/auth/refresh ----


async def test_admin_refresh(client, db):
    admin = await create_admin(db)
    rt_record, raw_token = await create_refresh_token_record(db, admin_id=admin.id)
    resp = await client.post(
        "/api/v1/admin/auth/refresh",
        json={"refresh_token": raw_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


# ---- POST /api/v1/admin/auth/logout ----


async def test_admin_logout(client, db):
    admin = await create_admin(db)
    rt_record, raw_token = await create_refresh_token_record(db, admin_id=admin.id)
    resp = await client.post(
        "/api/v1/admin/auth/logout",
        json={"refresh_token": raw_token},
    )
    assert resp.status_code == 204
