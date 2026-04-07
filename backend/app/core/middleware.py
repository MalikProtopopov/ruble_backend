"""HTTP middleware: tracks `users.last_seen_at` for authenticated requests.

Why a middleware (not a FastAPI dependency):
- Runs once per request regardless of how many endpoints share auth deps.
- Throttled via Redis SET NX EX so we write to Postgres at most once per
  LAST_SEEN_THROTTLE_MINUTES per user — typical traffic produces ~4 writes/hour
  per active user instead of one per request.
- Failure to update is non-fatal: tracking activity must never break a request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import jwt
from sqlalchemy import update
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.core.security import decode_token
from app.models import User

logger = get_logger(__name__)


class LastSeenMiddleware(BaseHTTPMiddleware):
    """Update `users.last_seen_at` for authenticated requests, throttled via Redis."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Run the request first — never block on tracking.
        response = await call_next(request)

        try:
            await self._touch(request)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("last_seen_touch_failed", error=str(exc))

        return response

    async def _touch(self, request: Request) -> None:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if not auth or not auth.lower().startswith("bearer "):
            return
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return

        try:
            payload = decode_token(token)
        except jwt.PyJWTError:
            return
        if payload.get("type") != "access":
            return
        # Only donor / patron tokens carry a `sub` that maps to users.id; admin
        # tokens have role=admin and live in the admins table.
        if payload.get("role") == "admin":
            return
        sub = payload.get("sub")
        if not sub:
            return
        try:
            user_id = UUID(sub)
        except (ValueError, TypeError):
            return

        # Throttle: only one DB write per user per LAST_SEEN_THROTTLE_MINUTES.
        # SET NX EX = "set if not exists, with TTL". If the key already exists
        # the call returns None and we skip the write.
        ttl = settings.LAST_SEEN_THROTTLE_MINUTES * 60
        was_set = await redis_client.set(f"last_seen:{user_id}", "1", nx=True, ex=ttl)
        if not was_set:
            return

        async with async_session_factory() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id, User.is_deleted == False)  # noqa: E712
                .values(last_seen_at=datetime.now(timezone.utc))
            )
            await session.commit()
