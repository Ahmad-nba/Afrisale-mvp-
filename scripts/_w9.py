import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/api/__init__.py", "")
w("app/services/message_service.py", r"""
import logging

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


def handle_inbound(db: Session, from_phone: str, text: str) -> str:
    customer = get_or_create_customer(db, from_phone)
    raw_in = (text or "").strip()

    ok, detail = input_guardrails.validate_inbound_message(text)
    save_message(db, customer.id, raw_in, "in")

    if not ok:
        reply = detail
        save_message(db, customer.id, reply, "out")
        try:
            africastalking.send_sms(normalize_phone(from_phone), reply)
        except Exception:
            logger.exception("send_sms after input rejection")
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
    try:
        africastalking.send_sms(normalize_phone(from_phone), safe_reply)
    except Exception:
        logger.exception("send_sms after reply")
    return safe_reply
""")

w("app/api/messages.py", r"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.schemas import WebhookPayload
from app.services.message_service import handle_inbound

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/webhook")
def webhook(body: WebhookPayload, db: Session = Depends(get_db)) -> dict:
    reply = handle_inbound(db, body.from_, body.text)
    return {"status": "ok", "reply": reply}
""")

w("main.py", r"""
import app.models.models  # noqa: F401 — register ORM metadata

from fastapi import FastAPI

from app.api.messages import router
from app.core.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Afrisale MVP")
app.include_router(router)
""")
print("api main")
