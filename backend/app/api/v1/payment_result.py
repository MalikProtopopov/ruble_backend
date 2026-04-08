"""HTTPS landing page for the YooKassa post-payment redirect.

YooKassa requires `confirmation.return_url` to be an HTTPS URL — it rejects
custom URI schemes like `porublyu://`. Without an HTTPS handler the user ends
up on YooKassa's default fallback page after confirming the payment, with no
way back to the mobile app.

This module exposes `GET /payment-result` which:
  1. Reads donation_id / transaction_id / subscription_id from the query string
     (passed in by `services/donation.py` and `services/subscription.py`).
  2. Returns a tiny HTML page that:
     - Immediately tries to open the `porublyu://payment-result` deep link
       (Universal Link / App Link if you've configured them, otherwise the
       custom scheme).
     - Falls back to a friendly "Возвращаемся в приложение..." message with
       a manual button if the deep link doesn't open within 1.5 seconds.

The page is intentionally tiny, no external assets, no tracking. It's a bridge,
not a real frontend.
"""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

router = APIRouter()


def _build_deep_link(
    donation_id: str | None,
    transaction_id: str | None,
    subscription_id: str | None,
) -> str:
    """Build the porublyu:// deep link with whatever IDs we have."""
    params: list[str] = []
    if donation_id:
        params.append(f"donation_id={donation_id}")
    if transaction_id:
        params.append(f"transaction_id={transaction_id}")
    if subscription_id:
        params.append(f"subscription_id={subscription_id}")
    qs = "&".join(params)
    return f"porublyu://payment-result{('?' + qs) if qs else ''}"


@router.get(
    "/payment-result",
    summary="Post-payment redirect handler",
    description=(
        "HTML-страница, на которую YooKassa возвращает пользователя после "
        "подтверждения платежа. Открывает приложение через deep link и "
        "показывает fallback-сообщение если приложение не открылось."
    ),
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def payment_result_handler(
    donation_id: str | None = Query(default=None),
    transaction_id: str | None = Query(default=None),
    subscription_id: str | None = Query(default=None),
):
    deep_link = _build_deep_link(donation_id, transaction_id, subscription_id)

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>По Рублю — оплата</title>
  <style>
    :root {{
      color-scheme: light dark;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      padding: 0;
      height: 100%;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f7f7f9;
      color: #1d1d1f;
    }}
    @media (prefers-color-scheme: dark) {{
      html, body {{ background: #1c1c1e; color: #f5f5f7; }}
    }}
    .wrap {{
      min-height: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 32px 24px;
      text-align: center;
    }}
    .logo {{
      font-size: 28px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    h1 {{
      font-size: 22px;
      margin: 24px 0 8px;
    }}
    p {{
      font-size: 16px;
      line-height: 1.5;
      max-width: 320px;
      opacity: 0.85;
    }}
    .spinner {{
      width: 48px;
      height: 48px;
      border-radius: 50%;
      border: 4px solid rgba(0,0,0,0.1);
      border-top-color: #4a90e2;
      animation: spin 0.8s linear infinite;
      margin: 16px auto;
    }}
    @media (prefers-color-scheme: dark) {{
      .spinner {{ border-color: rgba(255,255,255,0.15); border-top-color: #4a90e2; }}
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .btn {{
      display: inline-block;
      margin-top: 24px;
      padding: 14px 28px;
      background: #4a90e2;
      color: white;
      border-radius: 12px;
      text-decoration: none;
      font-weight: 600;
      font-size: 16px;
      box-shadow: 0 4px 12px rgba(74,144,226,0.3);
    }}
    .btn:active {{ transform: scale(0.97); }}
    .fallback {{ display: none; margin-top: 24px; }}
    .fallback.visible {{ display: block; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="logo">По Рублю</div>
    <div class="spinner" id="spinner"></div>
    <h1 id="title">Возвращаемся в приложение…</h1>
    <p id="subtitle">Если приложение не открылось автоматически, нажмите кнопку ниже.</p>
    <div class="fallback" id="fallback">
      <a href="{deep_link}" class="btn">Открыть приложение</a>
    </div>
  </div>
  <script>
    (function() {{
      var deepLink = {deep_link!r};
      // Try to open the deep link immediately.
      try {{
        window.location.href = deepLink;
      }} catch (e) {{}}
      // After 1.5s show the manual button (in case the OS didn't intercept).
      setTimeout(function() {{
        var fb = document.getElementById('fallback');
        if (fb) fb.classList.add('visible');
        var sp = document.getElementById('spinner');
        if (sp) sp.style.display = 'none';
      }}, 1500);
    }})();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})
