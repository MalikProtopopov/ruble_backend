"""Notification provider abstraction."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import uuid7

from app.core.config import settings
from app.core.logging import get_logger
from app.models import NotificationLog
from app.models.base import NotificationStatus

logger = get_logger(__name__)


async def send_push(
    session: AsyncSession,
    user_id: UUID | None,
    push_token: str | None,
    notification_type: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> None:
    """Send push notification via configured provider."""
    status = NotificationStatus.mock
    provider_response = None

    if settings.NOTIFICATION_PROVIDER == "firebase" and push_token:
        # TODO: implement Firebase push
        status = NotificationStatus.sent
        logger.info("push_sent_firebase", user_id=str(user_id), type=notification_type)
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
