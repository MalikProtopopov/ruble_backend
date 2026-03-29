"""Authentication service — OTP, JWT, token rotation."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.config import settings
from app.core.exceptions import AppError, BusinessLogicError, ForbiddenError
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models import Admin, OTPCode, RefreshToken, User

from app.domain.constants import OTP_TTL_MINUTES, OTP_MAX_ATTEMPTS, OTP_RATE_LIMIT_SECONDS

logger = get_logger(__name__)

_ph = PasswordHasher()


def _hash_otp(code: str) -> str:
    """Hash OTP code using argon2."""
    return _ph.hash(code)


def _verify_otp(code_hash: str, code: str) -> bool:
    """Verify OTP code against argon2 hash."""
    try:
        return _ph.verify(code_hash, code)
    except VerifyMismatchError:
        return False


def _hash_token(token: str) -> str:
    """Hash refresh token using SHA-256."""
    return hashlib.sha256(token.encode()).hexdigest()


# Keep backward-compatible alias
_hash_refresh_token = _hash_token


async def _check_otp_rate_limit(email: str) -> None:
    """Check Redis rate limit for OTP sending: max 5 per 60 seconds."""
    key = f"otp_rate:{email}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, OTP_RATE_LIMIT_SECONDS)
    if count > 5:
        raise BusinessLogicError(
            code="OTP_RATE_LIMIT",
            message="Слишком много запросов. Подождите минуту.",
        )


async def _create_user_tokens(session: AsyncSession, user: User) -> tuple[str, str]:
    """Create access + refresh token pair and store RefreshToken record."""
    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id)

    rt = RefreshToken(
        id=uuid7(),
        user_id=user.id,
        token_hash=_hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    session.add(rt)
    await session.flush()
    return access_token, refresh_token


async def send_otp(session: AsyncSession, email: str) -> dict:
    """Generate and 'send' OTP. Returns expires_in_seconds. Rate limited via Redis."""
    await _check_otp_rate_limit(email)

    code = f"{secrets.randbelow(10**6):06d}"
    otp = OTPCode(
        id=uuid7(),
        email=email,
        code_hash=_hash_otp(code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES),
    )
    session.add(otp)
    await session.flush()

    # Send OTP email
    from app.infrastructure.email import send_otp_email
    sent = await send_otp_email(email, code)
    if not sent:
        logger.warning("otp_email_failed", email=email)

    logger.info("otp_sent", email=email, sent=sent)
    return {"message": "OTP код отправлен", "expires_in_seconds": OTP_TTL_MINUTES * 60}


async def verify_otp(session: AsyncSession, email: str, code: str) -> dict:
    """Verify OTP, create user if needed, issue tokens."""
    now = datetime.now(timezone.utc)
    # Fetch ALL active (unused, not expired) OTPs for this email — not just the latest.
    # User may have received an earlier code while a newer one was sent.
    result = await session.execute(
        select(OTPCode)
        .where(OTPCode.email == email, OTPCode.is_used == False, OTPCode.expires_at > now)
        .order_by(OTPCode.created_at.desc())
    )
    otps = list(result.scalars().all())
    if not otps:
        raise BusinessLogicError(code="OTP_EXPIRED", message="OTP код истёк или не найден")

    # Try to match code against any active OTP
    matched_otp = None
    for otp in otps:
        if otp.attempts >= OTP_MAX_ATTEMPTS:
            continue
        if _verify_otp(otp.code_hash, code):
            matched_otp = otp
            break

    if matched_otp is None:
        # Increment attempts on the newest OTP
        otps[0].attempts += 1
        await session.flush()
        if otps[0].attempts >= OTP_MAX_ATTEMPTS:
            raise BusinessLogicError(code="OTP_MAX_ATTEMPTS", message="Превышено число попыток ввода OTP")
        raise BusinessLogicError(code="OTP_INVALID", message="Неверный OTP код")

    # Mark matched OTP and all older ones as used
    for otp in otps:
        otp.is_used = True
    await session.flush()

    # Find or create user
    user_result = await session.execute(select(User).where(User.email == email, User.is_deleted == False))
    user = user_result.scalar_one_or_none()
    is_new = False

    if user and not user.is_active:
        raise ForbiddenError(message="Ваш аккаунт деактивирован. Обратитесь в поддержку.")

    if user is None:
        user = User(id=uuid7(), email=email)
        session.add(user)
        await session.flush()
        is_new = True

    access_token, refresh_token = await _create_user_tokens(session, user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "is_new": is_new,
        },
    }


async def refresh_tokens(session: AsyncSession, refresh_token_str: str) -> dict:
    """Rotate refresh token. Detect replay attacks."""
    token_hash = _hash_refresh_token(refresh_token_str)
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt is None:
        raise AppError(code="INVALID_REFRESH_TOKEN", message="Refresh token не найден", status_code=401)
    if rt.is_revoked:
        raise AppError(code="INVALID_REFRESH_TOKEN", message="Refresh token отозван", status_code=401)
    if rt.expires_at < now:
        raise AppError(code="INVALID_REFRESH_TOKEN", message="Refresh token истёк", status_code=401)
    if rt.is_used:
        # Replay attack — revoke all tokens for this user/admin
        if rt.user_id:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == rt.user_id, RefreshToken.is_revoked == False)
                .values(is_revoked=True)
            )
        elif rt.admin_id:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.admin_id == rt.admin_id, RefreshToken.is_revoked == False)
                .values(is_revoked=True)
            )
        await session.flush()
        raise AppError(code="REPLAY_ATTACK_DETECTED", message="Обнаружено повторное использование токена. Все сессии отозваны.", status_code=401)

    rt.is_used = True
    await session.flush()

    # Determine subject
    if rt.user_id:
        user_result = await session.execute(select(User).where(User.id == rt.user_id))
        user = user_result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise AppError(code="INVALID_REFRESH_TOKEN", message="Пользователь не найден или деактивирован", status_code=401)
        access_token = create_access_token(user.id, user.role.value)
        new_refresh = create_refresh_token(user.id)
        new_rt = RefreshToken(id=uuid7(), user_id=user.id, token_hash=_hash_refresh_token(new_refresh), expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS))
    elif rt.admin_id:
        admin_result = await session.execute(select(Admin).where(Admin.id == rt.admin_id))
        admin = admin_result.scalar_one_or_none()
        if admin is None or not admin.is_active:
            raise AppError(code="INVALID_REFRESH_TOKEN", message="Администратор не найден или деактивирован", status_code=401)
        access_token = create_access_token(admin.id, "admin")
        new_refresh = create_refresh_token(admin.id)
        new_rt = RefreshToken(id=uuid7(), admin_id=admin.id, token_hash=_hash_refresh_token(new_refresh), expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS))
    else:
        raise AppError(code="INVALID_REFRESH_TOKEN", message="Невалидный токен", status_code=401)

    session.add(new_rt)
    await session.flush()

    return {"access_token": access_token, "refresh_token": new_refresh, "token_type": "bearer"}


async def logout(session: AsyncSession, refresh_token_str: str) -> None:
    """Revoke refresh token."""
    token_hash = _hash_refresh_token(refresh_token_str)
    await session.execute(
        update(RefreshToken).where(RefreshToken.token_hash == token_hash).values(is_revoked=True)
    )


async def admin_login(session: AsyncSession, email: str, password: str) -> dict:
    """Admin login with email + password."""
    result = await session.execute(select(Admin).where(Admin.email == email))
    admin = result.scalar_one_or_none()
    if admin is None:
        raise AppError(code="ADMIN_AUTH_FAILED", message="Неверный email или пароль", status_code=401)
    if not admin.is_active:
        raise AppError(code="ADMIN_AUTH_FAILED", message="Аккаунт деактивирован", status_code=401)
    try:
        _ph.verify(admin.password_hash, password)
    except VerifyMismatchError:
        raise AppError(code="ADMIN_AUTH_FAILED", message="Неверный email или пароль", status_code=401)

    access_token = create_access_token(admin.id, "admin")
    refresh_token = create_refresh_token(admin.id)

    rt = RefreshToken(
        id=uuid7(),
        admin_id=admin.id,
        token_hash=_hash_refresh_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    session.add(rt)
    await session.flush()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "admin": {"id": admin.id, "email": admin.email, "name": admin.name},
    }
