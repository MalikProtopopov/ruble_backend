"""Tests for the post-payment HTTPS landing page."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_payment_result_returns_html_with_deep_link(client):
    resp = await client.get("/payment-result?donation_id=abc-123")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "porublyu://payment-result?donation_id=abc-123" in body
    # Has the JS that triggers the deep link.
    assert "window.location.href" in body
    # Cache headers — never cache this.
    assert resp.headers.get("cache-control") == "no-store"


async def test_payment_result_works_without_params(client):
    """YooKassa might strip query params on redirect — page must still render."""
    resp = await client.get("/payment-result")
    assert resp.status_code == 200
    body = resp.text
    assert "porublyu://payment-result" in body  # bare deep link


async def test_payment_result_combines_transaction_and_subscription_ids(client):
    resp = await client.get(
        "/payment-result?transaction_id=tx-1&subscription_id=sub-2"
    )
    body = resp.text
    assert "transaction_id=tx-1" in body
    assert "subscription_id=sub-2" in body


async def test_payment_result_does_not_appear_in_openapi(client):
    """Internal bridge — must not pollute the public API spec."""
    resp = await client.get("/api/v1/openapi.json")
    schema = resp.json()
    paths = schema.get("paths", {})
    assert "/payment-result" not in paths


# ---------------------------------------------------------------------------
# Donation service now passes HTTPS return_url + always sends confirmation
# ---------------------------------------------------------------------------


async def test_donation_uses_https_return_url_with_payment_method_id(db):
    """Even when paying with a saved card, return_url must be HTTPS so the
    user lands on our bridge page if 3DS / test panel kicks in."""
    from unittest.mock import AsyncMock, patch

    from app.models import PaymentMethod
    from app.models.base import uuid7
    from app.services import donation as donation_service
    from tests.conftest import create_campaign, create_foundation, create_user

    user = await create_user(db)
    foundation = await create_foundation(db)
    campaign = await create_campaign(db, foundation)
    pm = PaymentMethod(
        id=uuid7(),
        user_id=user.id,
        provider="yookassa",
        provider_pm_id="saved-pm-1",
        card_last4="4242",
        is_default=True,
    )
    db.add(pm)
    await db.flush()

    fake_payment = AsyncMock(return_value={
        "id": "yk-x", "status": "pending", "payment_url": None, "payment_method_id": None,
    })
    with patch(
        "app.services.donation.yookassa_client.create_payment", new=fake_payment
    ):
        await donation_service.create_donation(
            db,
            campaign_id=campaign.id,
            amount_kopecks=10000,
            user_id=user.id,
            payment_method_id=pm.id,
            save_payment_method=False,
        )

    fake_payment.assert_awaited_once()
    call_kwargs = fake_payment.call_args.kwargs
    return_url = call_kwargs["return_url"]
    assert return_url.startswith("https://") or return_url.startswith("http://localhost")
    assert "/payment-result" in return_url
    assert "donation_id=" in return_url
    assert call_kwargs["payment_method_id"] == "saved-pm-1"


async def test_yookassa_client_always_sends_confirmation_block_when_return_url_set():
    """Saved-card payments must STILL get a confirmation.return_url so the
    user is redirected back to our bridge after a 3DS challenge."""
    from unittest.mock import AsyncMock, patch

    from app.services.yookassa import YooKassaClient

    captured: dict = {}

    class _FakeResp:
        status_code = 200
        text = "{}"
        def json(self_inner):
            return {
                "id": "yk-1",
                "status": "pending",
                "confirmation": None,
                "payment_method": None,
            }

    class _FakeClient:
        async def __aenter__(self_inner):
            return self_inner
        async def __aexit__(self_inner, *a):
            pass
        async def post(self_inner, url, json=None, **kw):
            captured["body"] = json
            return _FakeResp()

    client = YooKassaClient()
    client.shop_id = "test-shop"
    client.secret_key = "test-secret"
    with patch("httpx.AsyncClient", _FakeClient):
        await client.create_payment(
            amount_kopecks=10000,
            description="x",
            idempotence_key="k",
            return_url="https://api.example.com/payment-result?donation_id=xyz",
            payment_method_id="saved-pm",
        )

    body = captured["body"]
    assert body["payment_method_id"] == "saved-pm"
    # The crucial assertion: confirmation block IS present even with a saved PM
    assert "confirmation" in body
    assert body["confirmation"]["type"] == "redirect"
    assert body["confirmation"]["return_url"].startswith("https://")
