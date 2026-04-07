"""Notification provider — mock or Firebase Cloud Messaging."""

import asyncio
from uuid import UUID

from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.base import NotificationStatus, uuid7
from app.models.notification_log import NotificationLog

logger = get_logger(__name__)

_firebase_initialized = False


def _ensure_firebase():
    """Lazily initialize Firebase Admin SDK (once per process)."""
    global _firebase_initialized
    if _firebase_initialized:
        return
    import firebase_admin
    from firebase_admin import credentials

    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)
    _firebase_initialized = True
    logger.info("firebase_initialized")


def _build_fcm_message(push_token: str, title: str, body: str, data: dict | None):
    """Build a firebase_admin.messaging.Message."""
    from firebase_admin import messaging

    str_data = {k: str(v) for k, v in (data or {}).items()}

    return messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=str_data,
        token=push_token,
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                click_action="FLUTTER_NOTIFICATION_CLICK",
                sound="default",
            ),
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(badge=1, sound="default"),
            ),
        ),
    )


async def _clear_push_token(session: AsyncSession, user_id: UUID) -> None:
    """Clear invalid push token for a user."""
    from app.models.user import User

    await session.execute(
        sa_update(User).where(User.id == user_id).values(push_token=None)
    )
    logger.info("push_token_cleared", user_id=str(user_id))


async def send_push(
    session: AsyncSession,
    user_id: UUID | None,
    push_token: str | None,
    notification_type: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> None:
    """Send push notification via configured provider and log the result."""
    status = NotificationStatus.mock
    provider_response = None

    if settings.NOTIFICATION_PROVIDER == "firebase" and push_token:
        try:
            from firebase_admin import messaging

            _ensure_firebase()
            message = _build_fcm_message(push_token, title, body, data)
            result = await asyncio.to_thread(messaging.send, message)
            status = NotificationStatus.sent
            provider_response = {"message_id": result}
            logger.info("push_sent", user_id=str(user_id), type=notification_type, message_id=result)
        except Exception as exc:
            exc_name = type(exc).__name__
            status = NotificationStatus.failed
            provider_response = {"error": exc_name, "detail": str(exc)[:500]}
            logger.warning("push_failed", user_id=str(user_id), type=notification_type, error=exc_name)

            # Clear invalid tokens
            if exc_name in ("UnregisteredError", "SenderIdMismatchError", "InvalidArgumentError"):
                if user_id:
                    await _clear_push_token(session, user_id)
    else:
        logger.info("push_mock", user_id=str(user_id), type=notification_type, title=title)

    log = NotificationLog(
        id=uuid7(),
        user_id=user_id,
        push_token=push_token,
        notification_type=notification_type,
        title=title,
        body=body,
        data=data or {},
        status=status,
        provider_response=provider_response,
    )
    session.add(log)
    await session.flush()
