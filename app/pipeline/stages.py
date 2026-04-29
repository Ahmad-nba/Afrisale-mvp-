from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import inspect
from typing import Any

from sqlalchemy.orm import Session

from app.integrations import africastalking, twilio_whatsapp
from app.models.models import Customer, Message
from app.parlant_agent.session import AfrisaleSession
from app.services import media_service, message_service


logger = logging.getLogger("afrisale")


@dataclass
class OutboundEnvelope:
    """
    Result of an agent turn that the dispatch stage knows how to send.

    `text` is the primary message body. `media_url` is the public URL of the
    top-match product image (if any). `alternates_text` is an optional second
    text-only message listing additional matches.
    """

    text: str
    media_url: str = ""
    alternates_text: str = ""
    matches: list[dict[str, Any]] = field(default_factory=list)


def normalize_phone(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "")
    if s and not s.startswith("+") and s.isdigit():
        return "+" + s
    return s


async def normalize_inbound(from_raw: str, text_raw: str) -> dict[str, str]:
    """
    Returns: {"phone": str (E.164), "text": str (stripped)}
    Raises: ValueError if phone cannot be normalized
    """
    raw_phone = (from_raw or "").strip()
    if raw_phone.lower().startswith("whatsapp:"):
        raw_phone = raw_phone.split(":", 1)[1]
    phone = normalize_phone(raw_phone)
    if not phone:
        raise ValueError("Phone cannot be normalized.")
    return {"phone": phone, "text": (text_raw or "").strip()}


async def persist_inbound(
    db: Session,
    phone: str,
    text: str,
    *,
    channel: str = "whatsapp",
    has_attachments: bool = False,
) -> tuple[Customer, Message]:
    """
    Gets or creates Customer by phone. Saves inbound Message(direction='in')
    and returns the persisted ORM row so attachments can FK to its id.
    """
    customer = message_service.get_or_create_customer(db, phone)
    message_type = "media" if has_attachments and not text else (
        "mixed" if has_attachments else "text"
    )
    msg = Message(
        customer_id=customer.id,
        message=text or "",
        direction="in",
        channel=channel,
        message_type=message_type,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return customer, msg


async def persist_inbound_attachments(
    db: Session,
    message_id: int,
    descriptors: list[media_service.InboundMediaDescriptor],
) -> list[media_service.StoredAttachment]:
    """Wraps media_service so the runner stays thin."""
    if not descriptors:
        return []
    return media_service.ingest_inbound_attachments(db, message_id, descriptors)


async def call_agent(
    db: Session,
    customer: Customer,
    text: str,
    role: str,
    outbound_send: Callable[..., None] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> OutboundEnvelope:
    """
    Calls the agent runtime and returns an OutboundEnvelope describing what
    to send. The session may stash media_url and alternates on the engine
    via shared memory; we read them back here.
    """
    session = AfrisaleSession(customer_id=customer.id, role=role)
    reply, media_url, alternates, matches = await session.run_turn_with_media(
        db,
        user_text=text,
        attachments=attachments or [],
    )
    return OutboundEnvelope(
        text=str(reply or ""),
        media_url=str(media_url or ""),
        alternates_text=str(alternates or ""),
        matches=list(matches or []),
    )


async def persist_outbound(
    db: Session,
    customer: Customer,
    reply: str,
    *,
    channel: str = "whatsapp",
    has_media: bool = False,
) -> None:
    """Saves outbound Message(direction='out', content=reply) to DB."""
    message = Message(
        customer_id=customer.id,
        message=reply or "",
        direction="out",
        channel=channel,
        message_type="media" if has_media else "text",
    )
    db.add(message)
    db.commit()


async def dispatch_outbound(
    to: str,
    envelope: OutboundEnvelope,
    outbound_send: Callable[..., None] | None = None,
) -> None:
    """
    Sends the envelope through the WhatsApp/SMS path.

    For WhatsApp, when an image url is present we send the top match as a
    media message (image + caption), then optionally send the alternates as
    a follow-up text message.

    For SMS (no outbound_send), media is dropped to text only.
    """
    to_e164 = normalize_phone(to)
    try:
        if outbound_send is None:
            body = envelope.text
            if envelope.alternates_text:
                body = f"{body}\n\n{envelope.alternates_text}".strip()
            africastalking.send_sms(to_e164, body)
            return

        if envelope.media_url:
            twilio_whatsapp.send_whatsapp_media(
                to_e164,
                envelope.text,
                envelope.media_url,
            )
            if envelope.alternates_text.strip():
                twilio_whatsapp.send_whatsapp(to_e164, envelope.alternates_text.strip())
            return

        result = outbound_send(to_e164, envelope.text)
        if inspect.isawaitable(result):
            await result
    except Exception:
        logger.exception("dispatch_outbound_failed")
