"""YooKassa webhook endpoint."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logging import get_logger
from app.services import webhook as webhook_service
from app.services.yookassa import YooKassaClient

logger = get_logger(__name__)

router = APIRouter(tags=["webhooks"])


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, considering X-Forwarded-For from nginx."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post(
    "/yookassa",
    summary="Handle YooKassa webhook",
    description="Обработка событий от платёжной системы YooKassa",
)
async def yookassa_webhook(
    event: dict,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    # Verify webhook comes from YooKassa IP (skip in debug mode)
    if not settings.DEBUG:
        client_ip = _get_client_ip(request)
        if not YooKassaClient.is_webhook_ip_trusted(client_ip):
            logger.warning("yookassa_webhook_untrusted_ip", ip=client_ip)
            return JSONResponse(status_code=403, content={"error": "Forbidden"})

    result = await webhook_service.process_yookassa_webhook(session, event)
    return {"status": "ok"}
