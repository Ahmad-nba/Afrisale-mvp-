"""
Outbound WhatsApp via Twilio (sandbox uses whatsapp:+14155238886).
"""
from __future__ import annotations

import logging
from typing import Iterable

from twilio.rest import Client

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client() -> Client | None:
    sid = (settings.twilio_account_sid or "").strip()
    token = (settings.twilio_auth_token or "").strip()
    if not sid or not token:
        logger.warning("Twilio credentials missing; outbound WhatsApp skipped.")
        return None
    return Client(sid, token)


def format_whatsapp_address(e164: str) -> str:
    """Ensure Twilio WhatsApp 'to' / 'from' style: whatsapp:+15551234567"""
    raw = (e164 or "").strip().replace(" ", "")
    if raw.lower().startswith("whatsapp:"):
        return raw if raw.startswith("whatsapp:+") else f"whatsapp:+{raw.split(':', 1)[-1].lstrip('+')}"
    if raw.startswith("+"):
        return f"whatsapp:{raw}"
    return f"whatsapp:+{raw.lstrip('+')}"


def send_whatsapp(to_e164: str, message: str) -> None:
    """
    Send a WhatsApp text message. `to_e164` should be like +2567... (whatsapp: prefix added here).
    `from` uses TWILIO_WHATSAPP_FROM (default Twilio sandbox whatsapp:+14155238886).
    """
    client = _client()
    if not client:
        return
    from_addr = (settings.twilio_whatsapp_from or "whatsapp:+14155238886").strip()
    to_addr = format_whatsapp_address(to_e164)
    try:
        client.messages.create(from_=from_addr, body=message, to=to_addr)
        logger.info("Twilio WhatsApp text sent to %s", to_addr)
    except Exception:
        logger.exception("Twilio WhatsApp send failed")


def send_whatsapp_media(
    to_e164: str,
    body: str,
    media_url: str | Iterable[str],
) -> None:
    """
    Send a WhatsApp media message (image card with caption). Twilio accepts
    a list of URLs but on WhatsApp only the first is rendered as media.
    """
    client = _client()
    if not client:
        return
    if isinstance(media_url, str):
        media_urls = [media_url]
    else:
        media_urls = [u for u in media_url if u]
    media_urls = [u for u in media_urls if u]
    if not media_urls:
        send_whatsapp(to_e164, body)
        return

    from_addr = (settings.twilio_whatsapp_from or "whatsapp:+14155238886").strip()
    to_addr = format_whatsapp_address(to_e164)
    try:
        client.messages.create(
            from_=from_addr,
            body=body or "",
            to=to_addr,
            media_url=media_urls,
        )
        logger.info("Twilio WhatsApp media sent to %s media_count=%d", to_addr, len(media_urls))
    except Exception:
        logger.exception("Twilio WhatsApp media send failed; falling back to text")
        try:
            client.messages.create(from_=from_addr, body=body, to=to_addr)
        except Exception:
            logger.exception("Twilio WhatsApp text fallback also failed")
