"""
Exercise SQLite models, catalog writes, and memory_service (last 5 messages).
Run from repo root: python scripts/database_read_write_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path.replace("\\", "/")
os.environ.setdefault("SKIP_SMS_SEND", "true")

from app.core.database import Base, SessionLocal, engine  # noqa: E402
import app.models.models  # noqa: E402, F401
from app.memory.memory_service import format_memory_for_prompt, get_recent_messages  # noqa: E402
from app.models.models import Customer, Message  # noqa: E402
from app.services import catalog  # noqa: E402


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    catalog.add_product(db, "Test Tee", "Cotton shirt")
    db.close()
    db = SessionLocal()

    from sqlalchemy import select

    from app.models.models import ProductVariant

    v = db.scalars(select(ProductVariant)).first()
    assert v is not None, "expected default variant after add_product"
    assert v.price == 0

    c = Customer(phone_number="+19995550123")
    db.add(c)
    db.commit()
    db.refresh(c)

    for i, direction in enumerate(["in", "out", "in", "out", "in", "out"]):
        db.add(Message(customer_id=c.id, message=f"msg{i}", direction=direction))
    db.commit()

    recent = get_recent_messages(db, c.id, limit=5)
    assert len(recent) == 5
    assert [m.message for m in recent] == ["msg1", "msg2", "msg3", "msg4", "msg5"]

    mem = format_memory_for_prompt(recent)
    assert "Assistant: msg5" in mem

    db.close()
    print("PASS database_read_write_test")


if __name__ == "__main__":
    main()
