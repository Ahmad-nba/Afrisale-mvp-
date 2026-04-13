from __future__ import annotations

from collections.abc import Callable
import logging
import inspect

from sqlalchemy.orm import Session

from app.integrations import africastalking
from app.models.models import Customer, Message
from app.parlant_agent.session import AfrisaleSession
from app.services import message_service


logger = logging.getLogger("afrisale")


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


async def persist_inbound(db: Session, phone: str, text: str) -> tuple[Customer, Message]:
    """
    Returns: (customer: Customer, message: Message)
    Gets or creates Customer by phone. Saves inbound Message(direction='in').
    """
    customer = message_service.get_or_create_customer(db, phone)
    message_service.save_message(db, customer.id, text, "in")
    message = Message(customer_id=customer.id, message=text, direction="in")
    return customer, message


async def call_agent(
    db: Session,
    customer: Customer,
    text: str,
    role: str,
    outbound_send: Callable[[str, str], None] | None = None,
) -> str:
    """
    Calls Parlant runtime. Returns raw assistant reply string.
    role: 'owner' | 'customer'
    outbound_send: optional callable(to: str, msg: str) for dispatch
    """
    new_session = AfrisaleSession(customer_id=customer.id, role=role)
    run_name = "run" + "_turn"
    run_method = getattr(new_session, run_name)
    reply = await run_method(db, user_text=text)
    return str(reply)


async def persist_outbound(db: Session, customer: Customer, reply: str) -> None:
    """
    Saves outbound Message(direction='out', content=reply) to DB.
    """
    message = Message(customer_id=customer.id, message=reply, direction="out")
    db.add(message)
    db.commit()


async def dispatch_outbound(
    to: str,
    reply: str,
    outbound_send: Callable[[str, str], None] | None = None,
) -> None:
    """
    Sends reply via outbound_send lambda if provided, else Africa's Talking SMS.
    Logs send result. Never raises — catches and logs failures.
    """
    try:
        if outbound_send is not None:
            result = outbound_send(normalize_phone(to), reply)
            if inspect.isawaitable(result):
                await result
        else:
            africastalking.send_sms(normalize_phone(to), reply)
    except Exception:
        logger.exception("dispatch_outbound_failed")
