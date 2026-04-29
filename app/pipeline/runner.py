from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.guardrails.input_guardrail import InputGuardrail
from app.guardrails.output_formatting import OutputFormattingGuardrail
from app.guardrails.output_validation import OutputValidationGuardrail
from app.observability import logger as obs_logger
from app.pipeline import stages
from app.services import media_service


def _fire_logs(*coroutines: Awaitable[Any]) -> None:
    if not coroutines:
        return
    try:
        asyncio.ensure_future(asyncio.gather(*coroutines, return_exceptions=True))
    except RuntimeError:
        return


async def run_pipeline(
    db,
    from_raw: str,
    text_raw: str,
    owner_phone: str,
    outbound_send: Callable[..., None] | None = None,
    attachments: list[media_service.InboundMediaDescriptor] | None = None,
) -> str:
    """
    Full pipeline from raw inbound to dispatched reply.
    Returns the final user-facing text (after guardrails).
    `attachments` carries normalized inbound media descriptors when the
    channel supports them (e.g., Twilio WhatsApp).
    """
    descriptors = list(attachments or [])
    has_attachments = bool(descriptors)
    channel = "whatsapp" if outbound_send else "sms"

    normalized = await stages.normalize_inbound(from_raw, text_raw)
    phone, text = normalized["phone"], normalized["text"]

    customer, inbound_msg = await stages.persist_inbound(
        db,
        phone,
        text,
        channel=channel,
        has_attachments=has_attachments,
    )
    _fire_logs(obs_logger.log_inbound(customer.id, text, phone))

    stored_attachments = await stages.persist_inbound_attachments(
        db,
        message_id=inbound_msg.id,
        descriptors=descriptors,
    )
    attachments_for_agent = [a.to_dict() for a in stored_attachments]

    guardrail = InputGuardrail()
    valid, reason = guardrail.validate(text, has_attachments=bool(attachments_for_agent))
    _fire_logs(obs_logger.log_guardrail_decision("input", valid, reason, customer.id))
    if not valid:
        fallback = "I didn't quite get that. Could you send a bit more detail?"
        await stages.persist_outbound(db, customer, fallback, channel=channel)
        await stages.dispatch_outbound(
            phone,
            stages.OutboundEnvelope(text=fallback),
            outbound_send,
        )
        return fallback

    role = "owner" if phone == stages.normalize_phone(owner_phone) else "customer"
    envelope = await stages.call_agent(
        db,
        customer,
        text,
        role,
        outbound_send,
        attachments=attachments_for_agent,
    )

    validator = OutputValidationGuardrail()
    valid, vfallback = validator.validate(db, envelope.text, has_media=bool(envelope.media_url))
    _fire_logs(obs_logger.log_guardrail_decision("output_validation", valid, "", customer.id))
    if not valid:
        await stages.persist_outbound(db, customer, vfallback, channel=channel)
        await stages.dispatch_outbound(
            phone,
            stages.OutboundEnvelope(text=vfallback),
            outbound_send,
        )
        return vfallback

    formatter = OutputFormattingGuardrail()
    if envelope.media_url:
        envelope.text = formatter.format(envelope.text, channel=channel, as_caption=True)
        if envelope.alternates_text:
            envelope.alternates_text = formatter.format(envelope.alternates_text, channel=channel)
    else:
        envelope.text = formatter.format(envelope.text, channel=channel)
    _fire_logs(obs_logger.log_guardrail_decision("output_formatting", True, "", customer.id))

    persisted_text = envelope.text
    if envelope.alternates_text:
        persisted_text = f"{persisted_text}\n\n{envelope.alternates_text}".strip()
    await stages.persist_outbound(
        db,
        customer,
        persisted_text,
        channel=channel,
        has_media=bool(envelope.media_url),
    )
    _fire_logs(obs_logger.log_final_response(customer.id, persisted_text, channel))

    await stages.dispatch_outbound(phone, envelope, outbound_send)
    return persisted_text
