"""Integration tests for the authentication flow (OTP, JWT rotation, admin login)."""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.exceptions import AppError, BusinessLogicError, ForbiddenError
from app.models import OTPCode, RefreshToken, User
from app.models.base import UserRole
from app.services.auth import OTP_MAX_ATTEMPTS, verify_otp
from tests.conftest import create_admin, create_refresh_token_record, create_user

_ph = PasswordHasher()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_otp(
    db: AsyncSession,
    email: str,
    code: str = "123456",
    *,
    expired: bool = False,
    used: bool = False,
    attempts: int = 0,
) -> OTPCode:
    expires_at = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
        if expired
        else datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    otp = OTPCode(
        id=uuid7(),
        email=email,
        code_hash=_ph.hash(code),
        expires_at=expires_at,
        is_used=used,
        attempts=attempts,
    )
    db.add(otp)
    await db.flush()
    return otp


# ---------------------------------------------------------------------------
# send_otp
# ---------------------------------------------------------------------------


async def test_send_otp_success(db: AsyncSession):
    """send_otp should create an OTPCode row and return expires_in_seconds."""
    from app.services.auth import send_otp

    email = "otp-test@example.com"

    with patch("app.services.auth.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        mock_redis.setex = AsyncMock()
        result = await send_otp(db, email)

    assert result["expires_in_seconds"] == 600
    row = (
        await db.execute(select(OTPCode).where(OTPCode.email == email))
    ).scalar_one_or_none()
    assert row is not None
    assert row.is_used is False


async def test_send_otp_rate_limited(db: AsyncSession):
    """send_otp should raise OTP_RATE_LIMIT when redis key exists."""
    from app.services.auth import send_otp

    with patch("app.services.auth.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=6)
        mock_redis.expire = AsyncMock()
        with pytest.raises(BusinessLogicError) as exc_info:
            await send_otp(db, "ratelimit@example.com")
        assert exc_info.value.code == "OTP_RATE_LIMIT"


# ---------------------------------------------------------------------------
# verify_otp
# ---------------------------------------------------------------------------


async def test_verify_otp_success_new_user(db: AsyncSession):
    """Correct OTP for unknown email creates a user and returns is_new=True."""
    email = f"new-{uuid7().hex[:8]}@example.com"
    await _create_otp(db, email, "111111")

    result = await verify_otp(db, email, "111111")

    assert result["user"]["is_new"] is True
    assert result["access_token"]
    assert result["refresh_token"]
    # User should exist in DB
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one()
    assert user is not None


async def test_verify_otp_success_existing_user(db: AsyncSession):
    """Correct OTP for existing user returns is_new=False."""
    user = await create_user(db, email="existing@example.com")
    await _create_otp(db, "existing@example.com", "222222")

    result = await verify_otp(db, "existing@example.com", "222222")

    assert result["user"]["is_new"] is False
    assert str(result["user"]["id"]) == str(user.id)


async def test_verify_otp_wrong_code(db: AsyncSession):
    """Wrong code increments attempts and raises OTP_INVALID."""
    email = f"wrong-{uuid7().hex[:8]}@example.com"
    otp = await _create_otp(db, email, "333333")

    with pytest.raises(BusinessLogicError) as exc_info:
        await verify_otp(db, email, "000000")

    assert exc_info.value.code == "OTP_INVALID"
    await db.refresh(otp)
    assert otp.attempts == 1


async def test_verify_otp_expired(db: AsyncSession):
    """Expired OTP raises OTP_EXPIRED."""
    email = f"expired-{uuid7().hex[:8]}@example.com"
    await _create_otp(db, email, "444444", expired=True)

    with pytest.raises(BusinessLogicError) as exc_info:
        await verify_otp(db, email, "444444")

    assert exc_info.value.code == "OTP_EXPIRED"


async def test_verify_otp_max_attempts(db: AsyncSession):
    """OTP with max attempts reached raises OTP_MAX_ATTEMPTS."""
    email = f"maxatt-{uuid7().hex[:8]}@example.com"
    await _create_otp(db, email, "555555", attempts=OTP_MAX_ATTEMPTS)

    with pytest.raises(BusinessLogicError) as exc_info:
        await verify_otp(db, email, "555555")

    assert exc_info.value.code == "OTP_MAX_ATTEMPTS"


async def test_verify_otp_deactivated_user(db: AsyncSession):
    """OTP for a deactivated user raises ForbiddenError."""
    email = f"deact-{uuid7().hex[:8]}@example.com"
    await create_user(db, email=email, is_active=False)
    await _create_otp(db, email, "666666")

    with pytest.raises(ForbiddenError):
        await verify_otp(db, email, "666666")


# ---------------------------------------------------------------------------
# refresh_tokens
# ---------------------------------------------------------------------------


async def test_refresh_tokens_success(db: AsyncSession):
    """Valid unused refresh token is rotated: old marked used, new pair returned."""
    from app.services.auth import refresh_tokens

    user = await create_user(db)
    rt_record, raw_token = await create_refresh_token_record(db, user_id=user.id)

    result = await refresh_tokens(db, raw_token)

    assert result["access_token"]
    assert result["refresh_token"]
    assert result["refresh_token"] != raw_token

    await db.refresh(rt_record)
    assert rt_record.is_used is True


async def test_refresh_tokens_replay_attack(db: AsyncSession):
    """Reusing a used token revokes all tokens for that user."""
    from app.services.auth import refresh_tokens

    user = await create_user(db)
    rt_record, raw_token = await create_refresh_token_record(db, user_id=user.id)

    # First use — success
    await refresh_tokens(db, raw_token)

    # Second use — replay attack
    with pytest.raises(AppError) as exc_info:
        await refresh_tokens(db, raw_token)

    assert exc_info.value.code == "REPLAY_ATTACK_DETECTED"

    # All tokens for this user should be revoked
    rows = (
        await db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id,
                RefreshToken.is_revoked == False,
            )
        )
    ).scalars().all()
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------


async def test_logout_revokes_token(db: AsyncSession):
    """Logout revokes the refresh token."""
    from app.services.auth import logout

    user = await create_user(db)
    rt_record, raw_token = await create_refresh_token_record(db, user_id=user.id)

    await logout(db, raw_token)

    await db.refresh(rt_record)
    assert rt_record.is_revoked is True


# ---------------------------------------------------------------------------
# admin_login
# ---------------------------------------------------------------------------


async def test_admin_login_success(db: AsyncSession):
    """Admin with correct credentials gets tokens."""
    from app.services.auth import admin_login

    admin = await create_admin(db, email="admin@example.com", password="Secure123!")

    result = await admin_login(db, "admin@example.com", "Secure123!")

    assert result["access_token"]
    assert result["refresh_token"]
    assert str(result["admin"]["id"]) == str(admin.id)


async def test_admin_login_wrong_password(db: AsyncSession):
    """Wrong password raises ADMIN_AUTH_FAILED."""
    from app.services.auth import admin_login

    await create_admin(db, email="admin2@example.com", password="Correct123")

    with pytest.raises(AppError) as exc_info:
        await admin_login(db, "admin2@example.com", "Wrong456")

    assert exc_info.value.code == "ADMIN_AUTH_FAILED"


async def test_admin_login_deactivated(db: AsyncSession):
    """Deactivated admin raises ADMIN_AUTH_FAILED."""
    from app.services.auth import admin_login

    await create_admin(db, email="dead-admin@example.com", password="Pass123", is_active=False)

    with pytest.raises(AppError) as exc_info:
        await admin_login(db, "dead-admin@example.com", "Pass123")

    assert exc_info.value.code == "ADMIN_AUTH_FAILED"
