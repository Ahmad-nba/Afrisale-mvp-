"""
Outbound WhatsApp via Twilio (sandbox uses whatsapp:+14155238886).
"""
from __future__ import annotations

import logging

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
    Send a WhatsApp message. `to_e164` should be like +2567... (whatsapp: prefix added here).
    `from` uses TWILIO_WHATSAPP_FROM (default Twilio sandbox whatsapp:+14155238886).
    """
    client = _client()
    if not client:
        return
    from_addr = (settings.twilio_whatsapp_from or "whatsapp:+14155238886").strip()
    to_addr = format_whatsapp_address(to_e164)
    try:
        client.messages.create(from_=from_addr, body=message, to=to_addr)
        logger.info("Twilio WhatsApp sent to %s", to_addr)
    except Exception:
        logger.exception("Twilio WhatsApp send failed")
