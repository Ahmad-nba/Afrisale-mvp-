"""
Inbound media ingestion service.

Pipeline for an inbound WhatsApp media item:
  1. Receive Twilio media descriptor from the webhook.
  2. Download the file using authenticated Twilio creds.
  3. Validate MIME and size against config.
  4. Upload a durable copy to GCS.
  5. Persist a `MessageAttachment` row tied to the inbound message.
  6. Hand back a serializable summary the pipeline can pass to the agent.

Outbound media for catalog cards is handled separately in the dispatch
stage; this module focuses on inbound persistence.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations import gcs, twilio_media
from app.models.models import MessageAttachment

logger = logging.getLogger(__name__)


@dataclass
class InboundMediaDescriptor:
    """Normalized inbound media reference seen by the pipeline."""

    provider: str
    provider_url: str
    mime_type: str


@dataclass
class StoredAttachment:
    """Result returned to the pipeline after persistence."""

    id: int
    kind: str
    mime_type: str
    gcs_uri: str
    public_url: str
    bytes_size: int

    def to_dict(self) -> dict:
        return asdict(self)


def _allowed_mimes() -> set[str]:
    raw = (settings.image_allowed_mimes or "").strip()
    return {m.strip().lower() for m in raw.split(",") if m.strip()}


def _kind_for_mime(mime: str) -> str:
    mime_low = (mime or "").lower()
    if mime_low.startswith("image/"):
        return "image"
    if mime_low.startswith("video/"):
        return "video"
    if mime_low.startswith("audio/"):
        return "audio"
    return "document"


def _safe_object_name(mime: str) -> str:
    ext = ".bin"
    mime_low = (mime or "").lower()
    if "/" in mime_low:
        candidate = mime_low.split("/", 1)[1]
        candidate = candidate.split(";", 1)[0].strip()
        if candidate and candidate.replace("+", "").replace("-", "").isalnum():
            ext = "." + candidate
    return f"inbound/{int(time.time())}_{uuid.uuid4().hex}{ext}"


def parse_twilio_form_attachments(form: dict) -> list[InboundMediaDescriptor]:
    """
    Reads Twilio's NumMedia / MediaUrl{N} / MediaContentType{N} fields from
    a webhook form snapshot and returns normalized descriptors.
    """
    try:
        num = int(str(form.get("NumMedia", "0")).strip() or "0")
    except ValueError:
        num = 0
    descriptors: list[InboundMediaDescriptor] = []
    for idx in range(max(0, num)):
        url = str(form.get(f"MediaUrl{idx}", "") or "").strip()
        mime = str(form.get(f"MediaContentType{idx}", "") or "").strip()
        if not url:
            continue
        descriptors.append(
            InboundMediaDescriptor(
                provider="twilio",
                provider_url=url,
                mime_type=mime or "application/octet-stream",
            )
        )
    return descriptors


def ingest_inbound_attachments(
    db: Session,
    message_id: int,
    descriptors: list[InboundMediaDescriptor],
) -> list[StoredAttachment]:
    """
    Downloads each descriptor, archives to GCS, and writes attachment rows.
    Failures on a single attachment are logged and skipped so a partial set
    can still drive the agent turn.
    """
    if not descriptors:
        return []

    allowed = _allowed_mimes()
    max_bytes = int(settings.image_max_bytes or 0)
    stored: list[StoredAttachment] = []

    for descriptor in descriptors:
        try:
            payload = twilio_media.download_media(
                descriptor.provider_url,
                expected_mime=descriptor.mime_type,
            )
        except Exception:
            logger.exception("inbound_media_download_failed url=%s", descriptor.provider_url)
            continue

        mime = (payload.mime_type or descriptor.mime_type or "").lower()
        if allowed and mime not in allowed:
            logger.warning("inbound_media_mime_blocked mime=%s", mime)
            continue
        if max_bytes and payload.bytes_size > max_bytes:
            logger.warning(
                "inbound_media_too_large bytes=%d max=%d",
                payload.bytes_size,
                max_bytes,
            )
            continue

        try:
            object_name = _safe_object_name(mime)
            gcs_uri = gcs.upload_bytes(object_name, payload.content, mime)
            public_url = gcs.public_https_url(gcs_uri)
        except Exception:
            logger.exception("inbound_media_gcs_upload_failed mime=%s", mime)
            continue

        attachment = MessageAttachment(
            message_id=int(message_id),
            kind=_kind_for_mime(mime),
            mime_type=mime,
            provider=descriptor.provider or "twilio",
            provider_url=descriptor.provider_url,
            gcs_uri=gcs_uri,
            public_url=public_url,
            bytes_size=int(payload.bytes_size),
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)

        stored.append(
            StoredAttachment(
                id=int(attachment.id),
                kind=attachment.kind,
                mime_type=attachment.mime_type,
                gcs_uri=attachment.gcs_uri,
                public_url=attachment.public_url,
                bytes_size=int(attachment.bytes_size),
            )
        )

    return stored


def get_attachment(db: Session, attachment_id: int) -> Optional[MessageAttachment]:
    return db.get(MessageAttachment, int(attachment_id))
