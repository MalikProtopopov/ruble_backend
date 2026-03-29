"""Tests for /api/v1/auth/ endpoints."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from argon2 import PasswordHasher
from app.models.base import uuid7

from app.models import OTPCode
from tests.conftest import auth_header, create_refresh_token_record, create_user

_ph = PasswordHasher()

pytestmark = pytest.mark.asyncio


# ---- POST /api/v1/auth/send-otp ----


async def test_send_otp_success(client, db):
    with patch("app.services.auth.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        mock_redis.setex = AsyncMock()
        resp = await client.post(
            "/api/v1/auth/send-otp",
            json={"email": "otp-test@example.com"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in_seconds"] == 600
    assert "message" in body


async def test_send_otp_invalid_email(client):
    resp = await client.post(
        "/api/v1/auth/send-otp",
        json={"email": "not-an-email"},
    )
    assert resp.status_code == 422


# ---- POST /api/v1/auth/verify-otp ----


async def test_verify_otp_success(client, db):
    email = f"verify-{uuid7().hex[:8]}@test.com"
    otp = OTPCode(
        id=uuid7(),
        email=email,
        code_hash=_ph.hash("123456"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(otp)
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "code": "123456"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["user"]["is_new"] is True
    assert body["user"]["email"] == email


async def test_verify_otp_invalid_code(client, db):
    email = f"bad-code-{uuid7().hex[:8]}@test.com"
    otp = OTPCode(
        id=uuid7(),
        email=email,
        code_hash=_ph.hash("123456"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(otp)
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "code": "000000"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "OTP_INVALID"


async def test_verify_otp_expired(client, db):
    email = f"expired-{uuid7().hex[:8]}@test.com"
    otp = OTPCode(
        id=uuid7(),
        email=email,
        code_hash=_ph.hash("123456"),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db.add(otp)
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "code": "123456"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "OTP_EXPIRED"


# ---- POST /api/v1/auth/refresh ----


async def test_refresh_success(client, db):
    user = await create_user(db)
    rt_record, raw_token = await create_refresh_token_record(db, user_id=user.id)

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": raw_token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_refresh_invalid_token(client):
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "totally-invalid-token"},
    )
    assert resp.status_code == 401


# ---- POST /api/v1/auth/logout ----


async def test_logout_success(client, db, donor_headers):
    user = await create_user(db)
    rt_record, raw_token = await create_refresh_token_record(db, user_id=user.id)

    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": raw_token},
        headers=donor_headers,
    )
    assert resp.status_code == 204


async def test_logout_unauthorized(client):
    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "some-token"},
    )
    assert resp.status_code == 401
