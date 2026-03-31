"""
Print catalog from the app's configured DATABASE_URL (e.g. ./afrisale.db).
Does not call Gemini. Run from repo root: python scripts/read_local_db_catalog.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

# Import after .env so settings picks up DATABASE_URL
from app.core.database import SessionLocal  # noqa: E402
from app.services.catalog import get_products_formatted  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        text = get_products_formatted(db)
        print("DATABASE_URL:", os.environ.get("DATABASE_URL", "(default from settings)"))
        print("--- catalog from DB ---")
        print(text)
    finally:
        db.close()


if __name__ == "__main__":
    main()
