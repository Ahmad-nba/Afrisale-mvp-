from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Customer, Message


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
