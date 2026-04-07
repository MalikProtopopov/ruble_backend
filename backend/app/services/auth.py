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
from app.models.base import PushPlatform

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


def _refresh_ttl_days_for(user: User) -> int:
    return (
        settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS_ANONYMOUS
        if user.is_anonymous
        else settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )


async def _create_user_tokens(session: AsyncSession, user: User) -> tuple[str, str]:
    """Create access + refresh token pair and store RefreshToken record."""
    access_token = create_access_token(user.id, user.role.value)
    ttl_days = _refresh_ttl_days_for(user)
    refresh_token = create_refresh_token(user.id, ttl_days=ttl_days)

    rt = RefreshToken(
        id=uuid7(),
        user_id=user.id,
        token_hash=_hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=ttl_days),
    )
    session.add(rt)
    await session.flush()
    return access_token, refresh_token


async def device_register(
    session: AsyncSession,
    *,
    device_id: str,
    push_token: str | None = None,
    push_platform: str | None = None,
    timezone_name: str | None = None,
) -> dict:
    """Find-or-create an anonymous user by device_id and issue tokens.

    Idempotent: same device_id always returns the same user (with fresh tokens).
    """
    result = await session.execute(
        select(User).where(User.device_id == device_id, User.is_deleted == False)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    is_new = False

    if user is None:
        user = User(
            id=uuid7(),
            email=None,
            device_id=device_id,
            is_anonymous=True,
            is_email_verified=False,
        )
        if timezone_name:
            user.timezone = timezone_name
        if push_token:
            user.push_token = push_token
        if push_platform:
            try:
                user.push_platform = PushPlatform(push_platform)
            except ValueError:
                pass
        session.add(user)
        await session.flush()
        is_new = True
    else:
        if not user.is_active:
            raise ForbiddenError(message="Ваш аккаунт деактивирован. Обратитесь в поддержку.")
        # Refresh push token / platform / timezone if client provided new values.
        if push_token and user.push_token != push_token:
            user.push_token = push_token
        if push_platform:
            try:
                user.push_platform = PushPlatform(push_platform)
            except ValueError:
                pass
        if timezone_name and user.timezone != timezone_name:
            user.timezone = timezone_name
        await session.flush()

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
            "is_anonymous": user.is_anonymous,
            "is_email_verified": user.is_email_verified,
        },
    }


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
    user_result = await session.execute(select(User).where(User.email == email, User.is_deleted == False))  # noqa: E712
    user = user_result.scalar_one_or_none()
    is_new = False

    if user and not user.is_active:
        raise ForbiddenError(message="Ваш аккаунт деактивирован. Обратитесь в поддержку.")

    if user is None:
        user = User(id=uuid7(), email=email, is_email_verified=True, is_anonymous=False)
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
            "is_anonymous": user.is_anonymous,
            "is_email_verified": user.is_email_verified,
        },
    }


async def link_email_verify_otp(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    email: str,
    code: str,
    allow_merge: bool = False,
) -> dict:
    """Link email to an anonymous account, or merge into an existing target account.

    Flow:
    1. Validate OTP for `email` (same logic as verify_otp).
    2. Load current (presumably anonymous) user.
    3. If no other user has this email → just attach email to current user.
    4. If another user has this email:
       - If allow_merge=False → raise EMAIL_ALREADY_LINKED with target id.
       - If allow_merge=True → merge current (source) into target, return tokens for target.
    """
    from app.services.account_merge import merge_anonymous_into  # avoid circular import

    now = datetime.now(timezone.utc)
    # Validate OTP exactly like verify_otp
    result = await session.execute(
        select(OTPCode)
        .where(OTPCode.email == email, OTPCode.is_used == False, OTPCode.expires_at > now)  # noqa: E712
        .order_by(OTPCode.created_at.desc())
    )
    otps = list(result.scalars().all())
    if not otps:
        raise BusinessLogicError(code="OTP_EXPIRED", message="OTP код истёк или не найден")

    matched_otp = None
    for otp in otps:
        if otp.attempts >= OTP_MAX_ATTEMPTS:
            continue
        if _verify_otp(otp.code_hash, code):
            matched_otp = otp
            break

    if matched_otp is None:
        otps[0].attempts += 1
        await session.flush()
        if otps[0].attempts >= OTP_MAX_ATTEMPTS:
            raise BusinessLogicError(code="OTP_MAX_ATTEMPTS", message="Превышено число попыток ввода OTP")
        raise BusinessLogicError(code="OTP_INVALID", message="Неверный OTP код")

    for otp in otps:
        otp.is_used = True
    await session.flush()

    # Load current user
    cur_result = await session.execute(
        select(User).where(User.id == current_user_id, User.is_deleted == False)  # noqa: E712
    )
    current = cur_result.scalar_one_or_none()
    if current is None or not current.is_active:
        raise AppError(code="USER_NOT_FOUND", message="Текущий пользователь не найден", status_code=401)

    # Look for target user with this email
    tgt_result = await session.execute(
        select(User).where(User.email == email, User.is_deleted == False)  # noqa: E712
    )
    target = tgt_result.scalar_one_or_none()

    if target is not None and target.id != current.id:
        # Email belongs to another account → merge required
        if not allow_merge:
            # Build a small preview so the mobile app can show "you are about to merge X donations"
            from sqlalchemy import func as sa_func
            from app.models import Donation, Subscription

            src_donations = await session.scalar(
                select(sa_func.count(Donation.id)).where(Donation.user_id == current.id)
            )
            src_subs = await session.scalar(
                select(sa_func.count(Subscription.id)).where(Subscription.user_id == current.id)
            )
            raise BusinessLogicError(
                code="EMAIL_ALREADY_LINKED",
                message="Этот email уже привязан к другому аккаунту. Подтвердите объединение аккаунтов.",
                details={
                    "target_user_id": str(target.id),
                    "source_donations_count": int(src_donations or 0),
                    "source_subscriptions_count": int(src_subs or 0),
                    "source_total_donated_kopecks": int(current.total_donated_kopecks or 0),
                },
            )
        if not target.is_active:
            raise ForbiddenError(message="Целевой аккаунт деактивирован.")
        if not current.is_anonymous:
            raise BusinessLogicError(
                code="MERGE_NOT_ALLOWED",
                message="Объединение возможно только из гостевого аккаунта.",
            )
        await merge_anonymous_into(session, source=current, target=target)
        # Revoke source refresh tokens (also done inside merge but be explicit).
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == current.id, RefreshToken.is_revoked == False)  # noqa: E712
            .values(is_revoked=True)
        )
        await session.flush()
        access_token, refresh_token = await _create_user_tokens(session, target)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": target.id,
                "email": target.email,
                "name": target.name,
                "role": target.role.value,
                "is_new": False,
                "is_anonymous": False,
                "is_email_verified": True,
            },
            "merged": True,
        }

    # No conflict — attach email to current user.
    current.email = email
    current.is_email_verified = True
    current.is_anonymous = False
    await session.flush()

    # Issue new tokens (now with regular non-anonymous TTL).
    access_token, refresh_token = await _create_user_tokens(session, current)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": current.id,
            "email": current.email,
            "name": current.name,
            "role": current.role.value,
            "is_new": False,
            "is_anonymous": False,
            "is_email_verified": True,
        },
        "merged": False,
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
        ttl_days = _refresh_ttl_days_for(user)
        new_refresh = create_refresh_token(user.id, ttl_days=ttl_days)
        new_rt = RefreshToken(
            id=uuid7(),
            user_id=user.id,
            token_hash=_hash_refresh_token(new_refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=ttl_days),
        )
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
