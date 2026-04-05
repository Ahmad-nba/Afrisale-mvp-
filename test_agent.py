"""
Run from repo root: python test_agent.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import app.models.models  # noqa: F401 — register ORM metadata

from app.agents.agents import run_agent
from app.core.database import Base, SessionLocal, engine

Base.metadata.create_all(bind=engine)


def new_session_state() -> dict:
    return {
        "current_state": "idle",
        "last_products_shown": [],
        "selected_product": None,
        "collected_order_fields": {},
        "customer_id": None,
    }


def main() -> None:
    print("=== AI Sales Agent Test Console ===")
    print("Type 'exit' to quit\n")

    db = SessionLocal()
    state = new_session_state()

    try:
        while True:
            user_input = input("User: ").strip()

            if user_input.lower() == "exit":
                print("Goodbye.")
                break

            print()

            result = run_agent(user_input, state, db)

            print(f"[INTENT] {result['intent']} ({result['input_type']}) | confidence={result['confidence']}")
            print(f"[STATE TRANSITION] {result['state_before']} -> {result['state_after']}")

            for tool in result["tools_called"]:
                print(f"[TOOL CALLED] {tool['name']}({tool['args']!r})")

            print("\n[RESPONSE]")
            print(result["response"])
            print()

    finally:
        db.close()


if __name__ == "__main__":
    main()
