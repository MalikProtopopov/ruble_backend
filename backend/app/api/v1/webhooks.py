"""YooKassa webhook endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.logging import get_logger
from app.services import webhook as webhook_service

logger = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post(
    "/yookassa",
    summary="Handle YooKassa webhook",
    description="Обработка событий от платёжной системы YooKassa",
)
async def yookassa_webhook(
    event: dict,
    session: AsyncSession = Depends(get_db_session),
):
    event_type = event.get("event")
    payment = event.get("object", {})
    payment_id = payment.get("id")
    metadata = payment.get("metadata", {})

    if event_type == "payment.succeeded":
        await webhook_service.handle_payment_succeeded(session, payment_id, metadata)
    elif event_type == "payment.canceled":
        reason = payment.get("cancellation_details", {}).get("reason")
        await webhook_service.handle_payment_canceled(session, payment_id, reason)
    else:
        logger.warning("unknown_webhook_event", event_type=event_type)

    return {"status": "ok"}
