"""Email sending service — SMTP provider for OTP delivery."""

import asyncio
import smtplib
import ssl
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _build_otp_html(code: str) -> str:
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 480px; margin: 0 auto; padding: 32px;">
        <h2 style="color: #1a1a2e; margin-bottom: 8px;">По Рублю</h2>
        <p style="color: #555; font-size: 16px;">Ваш код подтверждения:</p>
        <div style="background: #f0f4ff; border-radius: 12px; padding: 24px;
                    text-align: center; margin: 24px 0;">
            <span style="font-size: 36px; font-weight: 700; letter-spacing: 8px;
                         color: #1a1a2e;">{code}</span>
        </div>
        <p style="color: #888; font-size: 14px;">
            Код действителен 10 минут. Если вы не запрашивали код — просто проигнорируйте это письмо.
        </p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
        <p style="color: #aaa; font-size: 12px;">
            Благотворительная платформа «По Рублю»
        </p>
    </div>
    """


def _build_otp_text(code: str) -> str:
    return f"Ваш код подтверждения: {code}\n\nКод действителен 10 минут.\nПо Рублю"


async def send_otp_email(email: str, code: str) -> bool:
    """Send OTP code via email. Returns True if sent successfully."""
    if settings.EMAIL_PROVIDER == "mock":
        logger.info("email_mock", to=email, code=code)
        return True

    try:
        return await asyncio.to_thread(_send_smtp, email, code)
    except Exception as e:
        logger.error("email_send_failed", to=email, error=str(e))
        return False


def _send_smtp(to_email: str, code: str) -> bool:
    """Blocking SMTP send — runs in thread via asyncio.to_thread."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(f"Код подтверждения: {code}", "utf-8")
    msg["From"] = formataddr((str(Header("По Рублю", "utf-8")), settings.SMTP_USER))
    msg["To"] = to_email

    msg.attach(MIMEText(_build_otp_text(code), "plain", "utf-8"))
    msg.attach(MIMEText(_build_otp_html(code), "html", "utf-8"))

    context = ssl.create_default_context()

    if settings.SMTP_PORT == 465:
        # SSL (implicit TLS)
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context, timeout=15) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
    else:
        # STARTTLS (port 587)
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls(context=context)
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

    logger.info("email_sent", to=to_email)
    return True
