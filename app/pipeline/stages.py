from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import Customer, Message


async def normalize_inbound(from_raw: str, text_raw: str) -> dict[str, str]:
    """
    Returns: {"phone": str (E.164), "text": str (stripped)}
    Raises: ValueError if phone cannot be normalized
    """
    pass


async def persist_inbound(db: Session, phone: str, text: str) -> tuple[Customer, Message]:
    """
    Returns: (customer: Customer, message: Message)
    Gets or creates Customer by phone. Saves inbound Message(direction='in').
    """
    pass


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
    pass


async def persist_outbound(db: Session, customer: Customer, reply: str) -> None:
    """
    Saves outbound Message(direction='out', content=reply) to DB.
    """
    pass


async def dispatch_outbound(
    to: str,
    reply: str,
    outbound_send: Callable[[str, str], None] | None = None,
) -> None:
    """
    Sends reply via outbound_send lambda if provided, else Africa's Talking SMS.
    Logs send result. Never raises — catches and logs failures.
    """
    pass
