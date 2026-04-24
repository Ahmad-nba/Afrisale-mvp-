"""
Single Gemini invoke + tools path (requires GCP_PROJECT_ID + ADC).
Run from repo root: python scripts/agent_test.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["DATABASE_URL"] = "sqlite:///" + _db_path.replace("\\", "/")
os.environ.setdefault("SKIP_SMS_SEND", "true")

if not os.environ.get("GCP_PROJECT_ID"):
    print("SKIP agent_test: set GCP_PROJECT_ID in environment or .env at repo root")
    sys.exit(0)

from app.core.database import Base, SessionLocal, engine  # noqa: E402
import app.models.models  # noqa: E402, F401
from app.models.models import Customer  # noqa: E402
from app.parlant_agent.session import AfrisaleSession  # noqa: E402
from app.services import catalog  # noqa: E402


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    catalog.add_product(db, "Demo Hoodie", "Warm hoodie")
    db.close()

    db = SessionLocal()
    c = Customer(phone_number="+19995550999")
    db.add(c)
    db.commit()
    db.refresh(c)

    out = asyncio.run(AfrisaleSession(c.id, "customer").run_turn(db, "Please list all products using the catalog tool."))
    db.close()

    assert out and len(out) > 5, f"unexpected short reply: {out!r}"
    assert "Demo Hoodie" in out or "Variant" in out or "variant" in out.lower(), out
    print("PASS agent_test")
    print(out[:500])


if __name__ == "__main__":
    main()
