"""JWT authentication and role-based access control."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def _read_key(path: str) -> str:
    with open(path) as f:
        return f.read()


def create_access_token(subject: UUID, role: str, *, audience: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "aud": audience or settings.JWT_AUDIENCE,
        "iss": settings.JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _read_key(settings.JWT_PRIVATE_KEY_PATH), algorithm="RS256")


def create_refresh_token(subject: UUID, *, ttl_days: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    days = ttl_days if ttl_days is not None else settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    payload = {
        "sub": str(subject),
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),  # ensures uniqueness even within the same second
        "aud": settings.JWT_AUDIENCE,
        "iss": settings.JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(days=days),
    }
    return jwt.encode(payload, _read_key(settings.JWT_PRIVATE_KEY_PATH), algorithm="RS256")


def decode_token(token: str, *, audience: str | None = None) -> dict:
    return jwt.decode(
        token,
        _read_key(settings.JWT_PUBLIC_KEY_PATH),
        algorithms=["RS256"],
        audience=audience or settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def require_donor(user: dict = Depends(get_current_user)):
    """Any authenticated user (donor or patron)."""
    return user


async def require_patron(user: dict = Depends(get_current_user)):
    if user.get("role") != "patron":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patron role required")
    return user


async def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
):
    """Admin authentication — isolated token contour.

    Admin access tokens are signed with a dedicated audience (`JWT_ADMIN_AUDIENCE`)
    and verified against it here. A regular user/donor token (audience
    `JWT_AUDIENCE`) therefore fails signature/audience validation on admin
    endpoints and vice-versa — the two contours cannot be crossed even if a
    `role` claim were tampered with. (A fully separate signing keypair can be
    layered on later via config without touching call sites.)
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials, audience=settings.JWT_ADMIN_AUDIENCE)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return payload
