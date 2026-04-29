"""
Authenticated downloads for Twilio media URLs.

Twilio's MediaUrl* fields are short-lived and require basic auth using the
account SID and auth token. We download once and persist to GCS so the rest
of the system can rely on durable URIs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TwilioMediaPayload:
    content: bytes
    mime_type: str
    bytes_size: int
    final_url: str


def download_media(url: str, expected_mime: str | None = None) -> TwilioMediaPayload:
    """
    Downloads media from Twilio with basic auth. Twilio responds with a 302
    to a short-lived storage URL; httpx follows redirects automatically.

    Raises httpx.HTTPError on non-2xx responses.
    """
    sid = (settings.twilio_account_sid or "").strip()
    token = (settings.twilio_auth_token or "").strip()
    if not sid or not token:
        raise RuntimeError("Twilio credentials missing; cannot download media.")

    timeout = httpx.Timeout(30.0, connect=10.0)
    auth = (sid, token)
    with httpx.Client(timeout=timeout, follow_redirects=True, auth=auth) as client:
        response = client.get(url)
        response.raise_for_status()
        content = response.content
        mime_type = response.headers.get("content-type", expected_mime or "application/octet-stream")
        if ";" in mime_type:
            mime_type = mime_type.split(";", 1)[0].strip()
        final_url = str(response.url)

    payload = TwilioMediaPayload(
        content=content,
        mime_type=mime_type,
        bytes_size=len(content),
        final_url=final_url,
    )
    logger.info("twilio_media_download ok bytes=%d mime=%s", payload.bytes_size, payload.mime_type)
    return payload
