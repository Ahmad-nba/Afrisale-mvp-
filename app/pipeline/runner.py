from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.guardrails.input_guardrail import InputGuardrail
from app.guardrails.output_formatting import OutputFormattingGuardrail
from app.guardrails.output_validation import OutputValidationGuardrail
from app.observability.logger import (
    log_final_response,
    log_guardrail_decision,
    log_inbound,
)
from app.pipeline.stages import (
    call_agent,
    dispatch_outbound,
    normalize_inbound,
    normalize_phone,
    persist_inbound,
    persist_outbound,
)


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
    outbound_send: Callable[[str, str], None] | None = None,
) -> str:
    """
    Full pipeline from raw inbound to dispatched reply.
    Returns the final reply string (after guardrails).
    All observability logs are fired in parallel via asyncio.gather.
    """
    normalized = await normalize_inbound(from_raw, text_raw)
    phone, text = normalized["phone"], normalized["text"]

    customer, _ = await persist_inbound(db, phone, text)
    _fire_logs(log_inbound(customer.id, text, phone))

    guardrail = InputGuardrail()
    valid, reason = guardrail.validate(text)
    _fire_logs(log_guardrail_decision("input", valid, reason, customer.id))
    if not valid:
        fallback = "I didn't quite get that. Could you send a bit more detail?"
        await persist_outbound(db, customer, fallback)
        await dispatch_outbound(phone, fallback, outbound_send)
        return fallback

    role = "owner" if phone == normalize_phone(owner_phone) else "customer"
    raw_reply = await call_agent(db, customer, text, role, outbound_send)

    validator = OutputValidationGuardrail()
    valid, fallback = validator.validate(db, raw_reply)
    _fire_logs(log_guardrail_decision("output_validation", valid, "", customer.id))
    if not valid:
        await persist_outbound(db, customer, fallback)
        await dispatch_outbound(phone, fallback, outbound_send)
        return fallback

    channel = "whatsapp" if outbound_send else "sms"
    formatter = OutputFormattingGuardrail()
    final_reply = formatter.format(raw_reply, channel=channel)
    _fire_logs(log_guardrail_decision("output_formatting", True, "", customer.id))

    await persist_outbound(db, customer, final_reply)
    _fire_logs(log_final_response(customer.id, final_reply, channel))
    await dispatch_outbound(phone, final_reply, outbound_send)
    return final_reply
