import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.agents import run_turn
from app.core.config import settings
from app.guardrails import input_guardrails, output_guardrails
from app.integrations import africastalking
from app.models.models import Customer, Message

logger = logging.getLogger(__name__)


def normalize_phone(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "")
    if s and not s.startswith("+") and s.isdigit():
        return "+" + s
    return s


def get_or_create_customer(db: Session, phone: str) -> Customer:
    phone = normalize_phone(phone)
    row = db.scalars(select(Customer).where(Customer.phone_number == phone)).first()
    if row:
        return row
    c = Customer(phone_number=phone)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def save_message(db: Session, customer_id: int, text: str, direction: str) -> None:
    db.add(Message(customer_id=customer_id, message=text, direction=direction))
    db.commit()


def _deliver_outbound(
    to_e164: str,
    message: str,
    *,
    outbound_send: Callable[[str, str], None] | None,
) -> None:
    to_norm = normalize_phone(to_e164)
    if outbound_send:
        try:
            outbound_send(to_norm, message)
        except Exception:
            logger.exception("outbound_send failed")
        return
    try:
        africastalking.send_sms(to_norm, message)
    except Exception:
        logger.exception("send_sms failed")


def handle_inbound(
    db: Session,
    from_phone: str,
    text: str,
    *,
    outbound_send: Callable[[str, str], None] | None = None,
) -> str:
    customer = get_or_create_customer(db, from_phone)
    raw_in = (text or "").strip()

    ok, detail = input_guardrails.validate_inbound_message(text)
    save_message(db, customer.id, raw_in, "in")

    if not ok:
        reply = detail
        save_message(db, customer.id, reply, "out")
        _deliver_outbound(from_phone, reply, outbound_send=outbound_send)
        return reply

    role = (
        "owner"
        if normalize_phone(from_phone) == normalize_phone(settings.owner_phone)
        else "customer"
    )

    try:
        raw_reply = run_turn(db, role, customer.id, detail)
    except Exception:
        logger.exception("run_turn failed")
        raw_reply = "Sorry, something went wrong. Please try again shortly."

    safe_reply = output_guardrails.validate_assistant_text(db, raw_reply)
    save_message(db, customer.id, safe_reply, "out")
    _deliver_outbound(from_phone, safe_reply, outbound_send=outbound_send)
    return safe_reply
