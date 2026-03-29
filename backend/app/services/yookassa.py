"""YooKassa API client (stub/wrapper)."""

import uuid

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class YooKassaClient:
    """Wrapper around the YooKassa HTTP API.

    Currently returns mock data. Replace with real httpx calls
    when integrating with production YooKassa.
    """

    def __init__(self) -> None:
        self.shop_id = settings.YOOKASSA_SHOP_ID
        self.secret_key = settings.YOOKASSA_SECRET_KEY

    async def create_payment(
        self,
        amount_kopecks: int,
        description: str,
        idempotence_key: str,
        return_url: str,
        save_payment_method: bool = False,
        payment_method_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create payment via YooKassa API.

        Returns dict with keys: id, payment_url, status.
        """
        # TODO: Implement actual YooKassa API call via httpx
        # POST https://api.yookassa.ru/v3/payments
        # Auth: Basic(shop_id, secret_key)
        # Idempotence-Key header
        mock_id = str(uuid.uuid4())
        payment_url = f"https://yookassa.ru/pay/{idempotence_key}"

        logger.info(
            "yookassa_payment_created_mock",
            payment_id=mock_id,
            amount_kopecks=amount_kopecks,
            save_payment_method=save_payment_method,
            idempotence_key=idempotence_key,
        )

        return {
            "id": mock_id,
            "payment_url": payment_url,
            "status": "pending",
        }

    async def create_recurring_payment(
        self,
        amount_kopecks: int,
        description: str,
        idempotence_key: str,
        payment_method_id: str,
        metadata: dict | None = None,
    ) -> dict:
        """Create a recurring (auto) payment using a saved payment method.

        Returns dict with keys: id, status.
        """
        # TODO: Implement actual YooKassa API call via httpx
        mock_id = str(uuid.uuid4())

        logger.info(
            "yookassa_recurring_payment_mock",
            payment_id=mock_id,
            amount_kopecks=amount_kopecks,
            payment_method_id=payment_method_id,
            idempotence_key=idempotence_key,
        )

        return {
            "id": mock_id,
            "status": "pending",
        }

    async def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify YooKassa webhook IP or signature.

        YooKassa webhooks are verified by IP whitelist rather than HMAC.
        This method is a placeholder for that check.
        """
        # TODO: Implement IP whitelist verification
        # YooKassa sends from specific IPs listed in their docs
        logger.warning("yookassa_webhook_signature_not_verified")
        return True


yookassa_client = YooKassaClient()
