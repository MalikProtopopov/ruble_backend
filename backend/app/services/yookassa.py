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
        payment_token: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create a payment via YooKassa API.

        Two acceptance modes, chosen by the caller:
        - **redirect** (default): no ``payment_token`` — YooKassa returns a
          ``confirmation_url`` the user opens to pay (the hosted checkout page).
        - **mobile SDK**: ``payment_token`` is the one-time token produced by the
          YooKassa iOS/Android SDK after the user enters card data in the native
          UI. We must NOT send a ``confirmation`` block in this mode — 3DS, if
          required, comes back as ``confirmation.confirmation_url`` in the
          response, which the SDK handles. ``payment_token`` and
          ``payment_method_id`` are mutually exclusive.

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

        if payment_token:
            # Mobile SDK flow — the token carries the payment method.
            body["payment_token"] = payment_token
        elif payment_method_id:
            body["payment_method_id"] = payment_method_id

        # Pass confirmation.return_url for the redirect flow only. For the SDK
        # flow (payment_token) YooKassa rejects/ignores a confirmation block —
        # 3DS is driven by the response's confirmation_url instead.
        #
        # For interactive payments (no saved card) this is where YooKassa
        # redirects after the user fills the form. For autopayments with a saved
        # card it's still needed because the issuer may require 3DS. YooKassa
        # rejects custom URI schemes (porublyu://...), so we point to an HTTPS
        # handler page which then opens the deep link in JS.
        if return_url and not payment_token:
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
                # SDK-token and saved-card payments need no redirect URL.
                "payment_url": None if (payment_method_id or payment_token) else f"https://yookassa.test/pay/{fake_id}",
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
            # 4xx = the request/payment was rejected (invalid or expired SDK
            # token, declined card, bad params). That's a client-handleable
            # condition — surface it as a clean 422 so the app can react
            # (e.g. re-tokenize), not a 500. 5xx / network → RuntimeError (500).
            if 400 <= resp.status_code < 500:
                from app.core.exceptions import BusinessLogicError

                try:
                    err = resp.json()
                except Exception:
                    err = {}
                raise BusinessLogicError(
                    code="PAYMENT_PROVIDER_ERROR",
                    message=err.get("description") or "Платёж отклонён платёжным провайдером",
                    details={"provider_code": err.get("code"), "parameter": err.get("parameter")},
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
            via_sdk_token=payment_token is not None,
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

    async def create_refund(
        self,
        payment_id: str,
        amount_kopecks: int,
        idempotence_key: str,
        description: str | None = None,
    ) -> dict:
        """Refund a previously succeeded payment via YooKassa API.

        Returns dict: {id, status} where status is typically 'succeeded'.
        """
        body: dict = {
            "amount": {"value": _kopecks_to_rub(amount_kopecks), "currency": "RUB"},
            "payment_id": payment_id,
        }
        if description:
            body["description"] = description[:250]

        # Test / unconfigured environments: skip the real API call.
        if not self.shop_id or not self.secret_key:
            fake_id = f"test-refund-{idempotence_key}"
            logger.info("yookassa_create_refund_mocked", refund_id=fake_id, payment_id=payment_id)
            return {"id": fake_id, "status": "succeeded"}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{YOOKASSA_API_URL}/refunds",
                json=body,
                auth=self._auth(),
                headers={"Idempotence-Key": idempotence_key, "Content-Type": "application/json"},
                timeout=30.0,
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "yookassa_create_refund_error",
                status=resp.status_code, body=resp.text, payment_id=payment_id,
            )
            raise RuntimeError(f"YooKassa refund error: {resp.status_code} {resp.text}")

        data = resp.json()
        logger.info("yookassa_refund_created", refund_id=data.get("id"), status=data.get("status"), payment_id=payment_id)
        return {"id": data["id"], "status": data["status"]}

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
