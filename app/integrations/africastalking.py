import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_sms(to: str, message: str) -> None:
    if settings.skip_sms_send:
        logger.info("skip_sms_send: would send to %s: %s", to, message[:120])
        return
    if not settings.at_username or not settings.at_api_key:
        logger.warning("Africa's Talking credentials missing; SMS not sent.")
        return
    payload = {
        "username": settings.at_username,
        "to": to,
        "message": message,
    }
    if settings.at_sender_id:
        payload["from"] = settings.at_sender_id
    headers = {
        "apiKey": settings.at_api_key,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(settings.at_base_url, data=payload, headers=headers)
        if r.status_code >= 400:
            logger.error("Africa's Talking error %s: %s", r.status_code, r.text[:500])
    except Exception:
        logger.exception("Failed to send SMS")
