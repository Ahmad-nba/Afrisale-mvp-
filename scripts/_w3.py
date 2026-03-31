import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/schemas/__init__.py", "")
w("app/schemas/schemas.py", r"""
from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    from_: str = Field(..., alias="from")
    text: str

    model_config = {"populate_by_name": True}
""")
w("app/memory/__init__.py", "")
w("app/memory/memory_service.py", r"""
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.models import Message


def get_recent_messages(db: Session, customer_id: int, limit: int = 5) -> list[Message]:
    q = (
        db.query(Message)
        .filter(Message.customer_id == customer_id)
        .order_by(desc(Message.id))
        .limit(limit)
    )
    rows = list(q)
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
""")
print("schemas memory")
