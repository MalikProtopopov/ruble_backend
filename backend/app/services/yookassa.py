"""YooKassa API client — real HTTP integration."""

import ipaddress
from decimal import Decimal

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

YOOKASSA_API_URL = "https://api.yookassa.ru/v3"

# IP ranges that YooKassa sends webhooks from (official docs)
YOOKASSA_WEBHOOK_IP_NETWORKS = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.156.11/32"),
    ipaddress.ip_network("77.75.156.35/32"),
    ipaddress.ip_network("77.75.154.128/25"),
    ipaddress.ip_network("2a02:5180::/32"),
]


def _kopecks_to_rub(kopecks: int) -> str:
    """Convert kopecks to rubles string for YooKassa API (e.g. 1050 -> '10.50')."""
    return str(Decimal(kopecks) / 100)


class YooKassaClient:
    """HTTP client for YooKassa Payments API."""

    def __init__(self) -> None:
        self.shop_id = settings.YOOKASSA_SHOP_ID
        self.secret_key = settings.YOOKASSA_SECRET_KEY

    def _auth(self) -> tuple[str, str]:
        return (self.shop_id, self.secret_key)

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
        """Create a payment via YooKassa API.

        For one-time payments: returns confirmation_url for redirect.
        For recurring with saved method: no confirmation needed.

        Returns dict: {id, payment_url, status, payment_method_id?}
        """
        body: dict = {
            "amount": {
                "value": _kopecks_to_rub(amount_kopecks),
                "currency": "RUB",
            },
            "capture": True,
            "description": description[:128],
            "metadata": metadata or {},
        }

        if payment_method_id:
            # Recurring payment with saved card — no user confirmation needed
            body["payment_method_id"] = payment_method_id
        else:
            # Interactive payment — user needs to confirm on YooKassa page
            body["confirmation"] = {
                "type": "redirect",
                "return_url": return_url,
            }

        if save_payment_method:
            body["save_payment_method"] = True

        # Test / unconfigured environments: skip the real API call.
        if not self.shop_id or not self.secret_key:
            fake_id = f"test-{idempotence_key}"
            logger.info(
                "yookassa_create_payment_mocked",
                payment_id=fake_id,
                amount_kopecks=amount_kopecks,
                save_payment_method=save_payment_method,
            )
            return {
                "id": fake_id,
                "status": "pending",
                "payment_url": None if payment_method_id else f"https://yookassa.test/pay/{fake_id}",
                "payment_method_id": fake_id if save_payment_method else None,
            }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{YOOKASSA_API_URL}/payments",
                json=body,
                auth=self._auth(),
                headers={
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "yookassa_create_payment_error",
                status=resp.status_code,
                body=resp.text,
                idempotence_key=idempotence_key,
            )
            raise RuntimeError(f"YooKassa API error: {resp.status_code} {resp.text}")

        data = resp.json()

        result = {
            "id": data["id"],
            "status": data["status"],
            "payment_url": None,
            "payment_method_id": None,
        }

        # Extract confirmation URL for interactive payments
        confirmation = data.get("confirmation")
        if confirmation and confirmation.get("confirmation_url"):
            result["payment_url"] = confirmation["confirmation_url"]

        # Extract saved payment method ID
        pm = data.get("payment_method")
        if pm and pm.get("saved"):
            result["payment_method_id"] = pm["id"]

        logger.info(
            "yookassa_payment_created",
            payment_id=data["id"],
            status=data["status"],
            amount_kopecks=amount_kopecks,
            save_payment_method=save_payment_method,
            has_confirmation_url=result["payment_url"] is not None,
        )

        return result

    async def create_recurring_payment(
        self,
        amount_kopecks: int,
        description: str,
        idempotence_key: str,
        payment_method_id: str,
        metadata: dict | None = None,
    ) -> dict:
        """Create an auto-payment using a saved payment method (no user confirmation)."""
        return await self.create_payment(
            amount_kopecks=amount_kopecks,
            description=description,
            idempotence_key=idempotence_key,
            return_url="",  # not used for recurring
            save_payment_method=False,
            payment_method_id=payment_method_id,
            metadata=metadata,
        )

    async def get_payment(self, payment_id: str) -> dict:
        """Get payment details from YooKassa to extract payment_method info."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{YOOKASSA_API_URL}/payments/{payment_id}",
                auth=self._auth(),
                timeout=15.0,
            )

        if resp.status_code != 200:
            logger.error("yookassa_get_payment_error", status=resp.status_code, payment_id=payment_id)
            raise RuntimeError(f"YooKassa API error: {resp.status_code}")

        return resp.json()

    @staticmethod
    def is_webhook_ip_trusted(ip: str) -> bool:
        """Check if the IP address belongs to YooKassa webhook senders."""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in network for network in YOOKASSA_WEBHOOK_IP_NETWORKS)


yookassa_client = YooKassaClient()
