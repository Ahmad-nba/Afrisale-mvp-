from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.models import Message


def get_recent_messages(db: Session, customer_id: int, limit: int = 5) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.customer_id == customer_id)
        .order_by(desc(Message.id))
        .limit(limit)
    )
    rows = list(db.scalars(stmt).all())
    rows.reverse()
    return rows


def format_memory_for_prompt(messages: list[Message]) -> str:
    lines: list[str] = []
    for m in messages:
        if m.direction == "in":
            lines.append(f"User: {m.message}")
        else:
            lines.append(f"Assistant: {m.message}")
    return "\n".join(lines) if lines else "(no prior messages)"
