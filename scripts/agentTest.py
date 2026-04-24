"""
Interactive customer agent: type what you want; the model may call get_products (and other
customer tools) once per line to answer from the real DATABASE_URL in .env.

Run from repo root:
  python scripts/agentTest.py

Environment: GCP_PROJECT_ID + ADC required (from .env / gcloud). Optional: AGENT_TEST_PHONE (default +19995550100).
Commands: blank line ignored; "quit" / "exit" to stop.
"""
from __future__ import annotations

import asyncio
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.guardrails import input_guardrails, output_guardrails  # noqa: E402
from app.parlant_agent.session import AfrisaleSession  # noqa: E402
from app.services.message_service import get_or_create_customer, save_message  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive agent vs local catalog DB")
    parser.add_argument(
        "--phone",
        default=None,
        help="Customer phone for session (default: env AGENT_TEST_PHONE or +19995550100)",
    )
    args = parser.parse_args()

    if not settings.gcp_project_id:
        print("Error: set GCP_PROJECT_ID in .env (or environment).")
        sys.exit(1)

    phone = args.phone or os.environ.get("AGENT_TEST_PHONE", "+19995550100")

    print("--- Afrisale interactive agent test ---")
    print(f"Using DB from settings and customer phone {phone}")
    print("Ask for products, sizes, colors, or whether something is in stock.")
    print("Type quit or exit to stop.\n")

    db = SessionLocal()
    try:
        customer = get_or_create_customer(db, phone)
        while True:
            try:
                line = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break
            if not line:
                continue
            if line.lower() in ("quit", "exit", "q"):
                print("Bye.")
                break

            ok, detail = input_guardrails.validate_inbound_message(line)
            if not ok:
                print(f"Assistant: {detail}\n")
                continue

            save_message(db, customer.id, line, "in")
            try:
                raw = asyncio.run(AfrisaleSession(customer.id, "customer").run_turn(db, detail))
            except Exception as exc:
                raw = f"Sorry, something went wrong: {exc}"
            reply = output_guardrails.validate_assistant_text(db, raw)
            save_message(db, customer.id, reply, "out")
            print(f"Assistant: {reply}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
