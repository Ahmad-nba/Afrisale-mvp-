"""
Afrisale — console agent harness
=================================
Simulates a WhatsApp conversation end-to-end through the real pipeline.
No webhooks, no Twilio, no network required. Uses the actual DB.

Usage:
    # As a customer (default)
    python test_agent_console.py

    # As the owner
    python test_agent_console.py --role owner

    # With a specific phone number
    python test_agent_console.py --phone +256700000001

    # Verbose: show full DB state after each turn
    python test_agent_console.py --verbose

    # Seed the DB with sample products first
    python test_agent_console.py --seed

Commands inside the chat:
    /quit or /exit   — end the session
    /reset           — start a new conversation (new session, same phone)
    /history         — print the last 10 messages from DB
    /tools           — list tools available to your current role
    /whoami          — show your role and phone
    /debug on|off    — toggle the instrumentation panel
    /role owner|customer — switch role mid-session (test only)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import textwrap
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ── silence noisy loggers so the UI is clean ──────────────────────────────
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("parlant").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)

# ── make sure we run from repo root ───────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure Unicode output does not crash on Windows cp1252 terminals.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── project imports ────────────────────────────────────────────────────────
from app.core.database import SessionLocal
from app.core.config import settings
from app.guardrails.input_guardrail import InputGuardrail
from app.guardrails.output_validation import OutputValidationGuardrail
from app.guardrails.output_formatting import OutputFormattingGuardrail
from app.parlant_agent.session import AfrisaleSession
from app.parlant_agent.tool_registry import build_customer_tools, build_owner_tools
from app.parlant_agent.guidelines import customer_guidelines, owner_guidelines
from app.services.message_service import get_or_create_customer, save_message, normalize_phone
from app.services import catalog as catalog_service
from app.services import orders as order_service
from app.models.models import Message

# ── Sanity-check Customer model field names at import time ────────────────
# Different projects name the phone column differently.
# Discover the real name once here so we can display it in /whoami and
# give a clear error if something is wired wrong — not a silent crash.
def _discover_customer_phone_field() -> str:
    """
    Inspect the Customer ORM model and return the actual column name used
    for the phone number. Falls back to None if none of the candidates match.
    """
    from app.models.models import Customer
    candidates = ["phone_number", "phone", "normalized_phone",
                  "whatsapp_number", "msisdn", "contact"]
    for col in candidates:
        if hasattr(Customer, col):
            return col
    # Last resort: scan all mapped column names
    try:
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(Customer)
        cols = [c.key for c in mapper.mapper.column_attrs]
        for c in cols:
            if "phone" in c.lower() or "number" in c.lower():
                return c
    except Exception:
        pass
    return None

CUSTOMER_PHONE_FIELD: str | None = _discover_customer_phone_field()

# ── ANSI palette ──────────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    # greens — agent / system
    GREEN   = "\033[38;5;78m"
    LGREEN  = "\033[38;5;120m"
    # blues — user
    BLUE    = "\033[38;5;75m"
    LBLUE   = "\033[38;5;117m"
    # yellows — debug / tools
    YELLOW  = "\033[38;5;220m"
    AMBER   = "\033[38;5;214m"
    # reds — guardrail blocks / errors
    RED     = "\033[38;5;203m"
    PINK    = "\033[38;5;211m"
    # neutral
    GRAY    = "\033[38;5;245m"
    WHITE   = "\033[38;5;255m"
    TEAL    = "\033[38;5;86m"
    PURPLE  = "\033[38;5;141m"

    @staticmethod
    def strip(text: str) -> str:
        """Remove all ANSI codes — for logging / plain output."""
        import re
        return re.sub(r'\033\[[0-9;]*m', '', text)


# ── terminal width helpers ─────────────────────────────────────────────────
def term_width() -> int:
    try:
        return min(os.get_terminal_size().columns, 100)
    except OSError:
        return 80


def hr(char="─", color=C.GRAY) -> str:
    return f"{color}{char * term_width()}{C.RESET}"


def box_line(text: str, width: int, pad=2) -> str:
    inner = width - (pad * 2) - 2
    return f"│{' ' * pad}{text[:inner]:<{inner}}{' ' * pad}│"


# ── Instrumentation collector ──────────────────────────────────────────────
class TurnTrace:
    """Collects everything that happens during one pipeline turn."""

    def __init__(self, user_text: str, phone: str, role: str):
        self.user_text   = user_text
        self.phone       = phone
        self.role        = role
        self.started_at  = time.perf_counter()

        # guardrail results
        self.input_valid    : bool | None = None
        self.input_reason   : str  = ""
        self.output_valid   : bool | None = None
        self.output_reason  : str  = ""

        # agent internals
        self.tool_calls     : list[dict] = []   # [{name, args, result, duration_ms}]
        self.raw_reply      : str  = ""
        self.final_reply    : str  = ""
        self.channel        : str  = "whatsapp"

        # timing
        self.guardrail_in_ms  : float = 0
        self.agent_ms         : float = 0
        self.guardrail_out_ms : float = 0
        self.total_ms         : float = 0

        # intent heuristic (computed from text, no LLM call)
        self.intent          : str  = ""
        self.intent_confidence: float = 0.0

    def finish(self):
        self.total_ms = (time.perf_counter() - self.started_at) * 1000

    def add_tool_call(self, name: str, args: dict, result: Any, duration_ms: float):
        self.tool_calls.append({
            "name": name,
            "args": args,
            "result": result,
            "duration_ms": duration_ms,
        })


# ── Simple intent heuristic (no LLM — just keyword matching) ──────────────
INTENT_MAP = [
    # (keywords, intent_label, weight)
    (["hi", "hello", "hey", "good morning", "good evening", "sawa", "habari"], "greeting",        1.0),
    (["order", "buy", "purchase", "want", "get me", "place"],                   "place_order",     0.9),
    (["status", "where", "track", "update", "my order"],                        "order_status",    0.9),
    (["search", "find", "look for", "do you have", "any"],                      "search_catalog",  0.85),
    (["list", "show", "catalog", "products", "what do you", "available"],       "browse_catalog",  0.85),
    (["price", "cost", "how much", "bei"],                                       "price_inquiry",   0.8),
    (["add product", "new product", "update stock", "update price", "restock"], "owner_manage",    0.95),
    (["list orders", "all orders", "show orders"],                               "owner_orders",    0.95),
    (["cancel", "return", "refund", "wrong"],                                    "complaint",       0.75),
    (["delivery", "deliver", "address", "location", "where to"],                "delivery_info",   0.8),
    (["thanks", "thank you", "ok", "okay", "cool", "asante"],                   "acknowledgement", 0.7),
]


def detect_intent(text: str) -> tuple[str, float]:
    lower = text.lower()
    best_intent = "general_inquiry"
    best_score  = 0.0
    for keywords, intent, weight in INTENT_MAP:
        hits = sum(1 for kw in keywords if kw in lower)
        if hits:
            score = weight * min(hits / len(keywords) * 3, 1.0)
            if score > best_score:
                best_score  = score
                best_intent = intent
    return best_intent, round(min(best_score, 1.0), 2)


# ── Tool call interceptor ──────────────────────────────────────────────────
def make_intercepted_tools(tools: list, trace: TurnTrace) -> list:
    """
    Wraps each tool handler so every invocation is recorded in the trace.
    Returns the same tool list with handlers replaced by instrumented versions.
    """
    instrumented = []
    for tool in tools:
        original_handler = (
            tool.get("handler") if isinstance(tool, dict)
            else getattr(tool, "handler", getattr(tool, "fn", None))
        )
        if not callable(original_handler):
            instrumented.append(tool)
            continue

        def make_wrapper(name, original):
            def wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    result = original(*args, **kwargs)
                    duration = (time.perf_counter() - t0) * 1000
                    trace.add_tool_call(name, kwargs, result, duration)
                    return result
                except Exception as e:
                    duration = (time.perf_counter() - t0) * 1000
                    trace.add_tool_call(name, kwargs, f"ERROR: {e}", duration)
                    raise
            return wrapper

        tool_name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", "unknown")
        wrapped = make_wrapper(tool_name, original_handler)

        if isinstance(tool, dict):
            patched = {**tool, "handler": wrapped}
        else:
            import copy
            patched = copy.copy(tool)
            if hasattr(patched, "handler"):
                patched.handler = wrapped
            elif hasattr(patched, "fn"):
                patched.fn = wrapped
        instrumented.append(patched)

    return instrumented


# ── Display helpers ────────────────────────────────────────────────────────
SESSION_START = datetime.now().strftime("%H:%M:%S")

def print_header(phone: str, role: str):
    w = term_width()
    print()
    print(f"{C.GREEN}{C.BOLD}{'═' * w}{C.RESET}")
    title = "  Afrisale — WhatsApp chat simulator"
    print(f"{C.GREEN}{C.BOLD}{title}{C.RESET}")
    print(f"{C.GRAY}  Session started  {SESSION_START}  │  Phone  {phone}  │  Role  {role.upper()}{C.RESET}")
    print(f"{C.GREEN}{C.BOLD}{'═' * w}{C.RESET}")
    print(f"{C.DIM}  Type a message to begin. /help for commands.{C.RESET}")
    print()


def print_user_bubble(text: str, phone: str):
    ts = datetime.now().strftime("%H:%M")
    prefix = f"{C.LBLUE}You ({phone[-6:]}){C.RESET}"
    print(f"\n{prefix}  {C.GRAY}{ts}{C.RESET}")
    wrapped = textwrap.fill(text, width=min(70, term_width() - 4))
    for line in wrapped.splitlines():
        print(f"  {C.BLUE}{line}{C.RESET}")


def print_agent_bubble(text: str, trace: TurnTrace):
    ts = datetime.now().strftime("%H:%M")
    channel_icon = "📱" if trace.channel == "whatsapp" else "💬"
    print(f"\n{C.LGREEN}{C.BOLD}Afrisale{C.RESET} {channel_icon}  {C.GRAY}{ts}{C.RESET}")
    wrapped = textwrap.fill(text, width=min(72, term_width() - 4))
    for line in wrapped.splitlines():
        print(f"  {C.WHITE}{line}{C.RESET}")


def print_debug_panel(trace: TurnTrace, verbose: bool = False):
    w = term_width()
    print(f"\n{C.GRAY}{'┄' * w}{C.RESET}")

    # ── Intent row ──
    conf_color = C.LGREEN if trace.intent_confidence >= 0.8 else (C.AMBER if trace.intent_confidence >= 0.5 else C.RED)
    conf_bar   = "█" * int(trace.intent_confidence * 10) + "░" * (10 - int(trace.intent_confidence * 10))
    print(
        f"  {C.GRAY}intent{C.RESET}   "
        f"{C.PURPLE}{C.BOLD}{trace.intent:<18}{C.RESET}  "
        f"confidence  {conf_color}{conf_bar}  {trace.intent_confidence:.0%}{C.RESET}"
    )

    # ── Guardrail row ──
    in_sym  = f"{C.LGREEN}✔ pass{C.RESET}" if trace.input_valid  else f"{C.RED}✘ block  {trace.input_reason}{C.RESET}"
    out_sym = f"{C.LGREEN}✔ pass{C.RESET}" if trace.output_valid else f"{C.RED}✘ block  {trace.output_reason}{C.RESET}"
    if trace.input_valid is None:
        in_sym = f"{C.GRAY}–{C.RESET}"
    if trace.output_valid is None:
        out_sym = f"{C.GRAY}–{C.RESET}"
    print(f"  {C.GRAY}guard-in{C.RESET} {in_sym}    {C.GRAY}guard-out{C.RESET} {out_sym}")

    # ── Tool calls ──
    if trace.tool_calls:
        print(f"  {C.GRAY}tools{C.RESET}")
        for tc in trace.tool_calls:
            args_str = json.dumps(tc["args"], ensure_ascii=False)
            if len(args_str) > 60:
                args_str = args_str[:57] + "..."
            result_preview = str(tc["result"])
            if len(result_preview) > 80:
                result_preview = result_preview[:77] + "..."
            print(
                f"    {C.TEAL}→ {tc['name']}{C.RESET}  "
                f"{C.GRAY}{args_str}  "
                f"({tc['duration_ms']:.0f}ms){C.RESET}"
            )
            if verbose:
                print(f"      {C.DIM}↳ {result_preview}{C.RESET}")
    else:
        print(f"  {C.GRAY}tools    {C.DIM}none called{C.RESET}")

    # ── Timing row ──
    print(
        f"  {C.GRAY}timing{C.RESET}  "
        f"guard-in {trace.guardrail_in_ms:.0f}ms  "
        f"agent {trace.agent_ms:.0f}ms  "
        f"guard-out {trace.guardrail_out_ms:.0f}ms  "
        f"{C.BOLD}total {trace.total_ms:.0f}ms{C.RESET}"
    )
    print(f"{C.GRAY}{'┄' * w}{C.RESET}")


def print_blocked(stage: str, reason: str, fallback: str):
    print(f"\n  {C.RED}⚠  blocked at {stage} — {reason}{C.RESET}")
    print(f"  {C.PINK}↳  {fallback}{C.RESET}")


def print_help():
    cmds = [
        ("/quit, /exit",    "end the session"),
        ("/reset",          "clear session context, keep phone"),
        ("/history",        "show last 10 messages from DB"),
        ("/tools",          "list tools available to your role"),
        ("/whoami",         "show role and phone number"),
        ("/debug on|off",   "toggle the instrumentation panel"),
        ("/role owner|customer", "switch role (test convenience)"),
        ("/seed",           "add sample products to DB"),
        ("/clear",          "clear the terminal"),
    ]
    print(f"\n{C.YELLOW}Commands:{C.RESET}")
    for cmd, desc in cmds:
        print(f"  {C.AMBER}{cmd:<28}{C.RESET}  {C.GRAY}{desc}{C.RESET}")
    print()


def print_tools(db, role: str):
    tools = build_customer_tools(db, 0) if role == "customer" else build_owner_tools(db)
    print(f"\n{C.YELLOW}Tools available to {role}:{C.RESET}")
    for t in tools:
        name = t.get("name") if isinstance(t, dict) else getattr(t, "name", "?")
        desc = t.get("description") if isinstance(t, dict) else getattr(t, "description", "")
        params = t.get("parameters", t.get("params", {})) if isinstance(t, dict) else getattr(t, "parameters", {})
        param_keys = list(params.keys()) if isinstance(params, dict) else []
        print(
            f"  {C.TEAL}{name:<22}{C.RESET}  {C.GRAY}{desc[:55]}{C.RESET}\n"
            f"  {C.DIM}{'':22}  params: {param_keys}{C.RESET}"
        )
    print()


def print_history(db, customer_id: int, limit: int = 10):
    msgs = (
        db.query(Message)
        .filter(Message.customer_id == customer_id)
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    msgs = list(reversed(msgs))
    print(f"\n{C.YELLOW}Last {len(msgs)} messages from DB:{C.RESET}")
    for m in msgs:
        arrow  = f"{C.BLUE}→{C.RESET}" if m.direction == "in" else f"{C.LGREEN}←{C.RESET}"
        who    = "you     " if m.direction == "in" else "afrisale"
        ts     = m.created_at.strftime("%H:%M") if hasattr(m, "created_at") and m.created_at else "--:--"
        body   = (m.message or "")[:80]
        print(f"  {arrow} {C.GRAY}{ts}{C.RESET}  {C.DIM}{who}{C.RESET}  {body}")
    print()


def seed_db(db):
    """Add sample products so the agent has something to work with."""
    from app.models.models import Product, ProductVariant
    existing = db.query(Product).count()
    if existing > 0:
        print(f"  {C.AMBER}DB already has {existing} products — skipping seed.{C.RESET}")
        return

    products = [
        {
            "name": "Basmati Rice",
            "description": "Premium long-grain basmati rice, aromatic and fluffy",
            "variants": [
                {"label": "1kg",  "price": 4500,  "stock": 50},
                {"label": "5kg",  "price": 20000, "stock": 20},
                {"label": "25kg", "price": 90000, "stock": 5},
            ],
        },
        {
            "name": "Maize Flour",
            "description": "Finely milled maize flour, ideal for ugali and porridge",
            "variants": [
                {"label": "2kg",  "price": 6000,  "stock": 40},
                {"label": "10kg", "price": 28000, "stock": 15},
            ],
        },
        {
            "name": "Cooking Oil",
            "description": "Refined vegetable cooking oil, cholesterol free",
            "variants": [
                {"label": "500ml", "price": 5500,  "stock": 60},
                {"label": "2L",    "price": 19000, "stock": 25},
                {"label": "5L",    "price": 44000, "stock": 10},
            ],
        },
        {
            "name": "Sugar",
            "description": "White refined sugar, ideal for home and commercial use",
            "variants": [
                {"label": "1kg",  "price": 5000,  "stock": 80},
                {"label": "5kg",  "price": 23000, "stock": 30},
            ],
        },
        {
            "name": "Omo Detergent",
            "description": "Multi-active laundry powder with fabric softener",
            "variants": [
                {"label": "500g", "price": 4200,  "stock": 45},
                {"label": "1kg",  "price": 7800,  "stock": 30},
            ],
        },
    ]

    for p_data in products:
        product = Product(
            name=p_data["name"],
            description=p_data["description"],
        )
        db.add(product)
        db.flush()
        for v_data in p_data["variants"]:
            variant = ProductVariant(
                product_id=product.id,
                size=v_data["label"],
                color="Default",
                price=v_data["price"],
                stock_quantity=v_data["stock"],
            )
            db.add(variant)

    db.commit()
    count = db.query(Product).count()
    print(f"  {C.LGREEN}✔  Seeded {count} products into DB.{C.RESET}")


# ── Core pipeline turn (instrumented) ─────────────────────────────────────
async def run_instrumented_turn(
    db,
    customer,
    phone: str,          # pass explicitly — never read from customer object
    text: str,
    role: str,
    debug: bool,
    verbose: bool,
) -> TurnTrace:
    """
    Runs the full pipeline for one turn and returns a populated TurnTrace.
    Mirrors run_pipeline exactly but collects instrumentation inline.

    NOTE: phone is passed in explicitly because the Customer model field name
    varies across projects (phone / phone_number / normalized_phone).
    We already have the canonical E.164 string in main() — no need to read
    it back off the ORM object.
    """
    trace = TurnTrace(user_text=text, phone=phone, role=role)

    # ── Intent detection (local heuristic, no LLM) ──
    trace.intent, trace.intent_confidence = detect_intent(text)

    # ── 1. Input guardrail ──
    t0 = time.perf_counter()
    ig = InputGuardrail()
    trace.input_valid, trace.input_reason = ig.validate(text)
    trace.guardrail_in_ms = (time.perf_counter() - t0) * 1000

    if not trace.input_valid:
        fallback = "I didn't quite get that. Could you rephrase with a bit more detail?"
        trace.raw_reply   = fallback
        trace.final_reply = fallback
        trace.output_valid = None  # never reached output guardrail
        save_message(db, customer_id=customer.id, direction="in", text=text)
        save_message(db, customer_id=customer.id, direction="out", text=fallback)
        trace.finish()
        if debug:
            print_debug_panel(trace, verbose)
        print_blocked("input guardrail", trace.input_reason, fallback)
        return trace

    save_message(db, customer_id=customer.id, direction="in", text=text)

    # ── 2. Parlant session ──
    t0 = time.perf_counter()
    try:
        # Build intercepted tools so tool calls get recorded in trace
        raw_tools = (
            build_customer_tools(db, customer.id)
            if role == "customer"
            else build_owner_tools(db)
        )
        intercepted = make_intercepted_tools(raw_tools, trace)

        session = AfrisaleSession(customer_id=customer.id, role=role)

        # Patch tool registry inside the session's run_turn to use intercepted tools
        with patch(
            f"app.parlant_agent.tool_registry.build_customer_tools",
            return_value=intercepted,
        ), patch(
            f"app.parlant_agent.tool_registry.build_owner_tools",
            return_value=intercepted,
        ):
            raw_reply = await session.run_turn(db=db, user_text=text)

        trace.raw_reply = raw_reply
    except Exception as e:
        raw_reply = "I'm having trouble right now. Please try again shortly."
        trace.raw_reply = raw_reply
        print(f"  {C.RED}Agent error: {e}{C.RESET}", file=sys.stderr)
    trace.agent_ms = (time.perf_counter() - t0) * 1000

    # ── 3. Output validation ──
    t0 = time.perf_counter()
    ov = OutputValidationGuardrail()
    trace.output_valid, fallback = ov.validate(db, raw_reply)
    trace.guardrail_out_ms = (time.perf_counter() - t0) * 1000

    if not trace.output_valid:
        trace.final_reply = fallback
        trace.output_reason = "validation_failed"
        save_message(db, customer_id=customer.id, direction="out", text=fallback)
        trace.finish()
        if debug:
            print_debug_panel(trace, verbose)
        print_blocked("output validation", trace.output_reason, fallback)
        return trace

    # ── 4. Output formatting ──
    trace.channel = "whatsapp"
    of = OutputFormattingGuardrail()
    trace.final_reply = of.format(raw_reply, channel=trace.channel)

    save_message(db, customer_id=customer.id, direction="out", text=trace.final_reply)
    trace.finish()
    return trace


# ── Main REPL ──────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Afrisale console chat simulator")
    parser.add_argument("--role",    default="customer", choices=["customer", "owner"],
                        help="Start as customer or owner")
    parser.add_argument("--phone",   default=None,
                        help="Phone number (E.164). Defaults to a test number per role.")
    parser.add_argument("--verbose", action="store_true",
                        help="Show tool result previews in debug panel")
    parser.add_argument("--debug",   action="store_true", default=True,
                        help="Show debug panel (on by default)")
    parser.add_argument("--no-debug", dest="debug", action="store_false",
                        help="Hide debug panel")
    parser.add_argument("--seed",    action="store_true",
                        help="Seed DB with sample products before starting")
    args = parser.parse_args()

    # Resolve phone
    default_phones = {
        "customer": "+256700000001",
        "owner":    settings.owner_phone or "+256700000099",
    }
    phone = args.phone or default_phones[args.role]
    role  = args.role
    debug = args.debug

    db = SessionLocal()

    try:
        # ── Validate model shape before the REPL starts ──────────────────
        if CUSTOMER_PHONE_FIELD is None:
            print(
                f"\n{C.RED}{C.BOLD}ERROR: cannot find phone column on Customer model.{C.RESET}\n"
                f"{C.AMBER}Open app/models/models.py and check what the phone field is called.\n"
                f"Then add it to the 'candidates' list in _discover_customer_phone_field().{C.RESET}\n"
            )
            sys.exit(1)
        else:
            # Emit a dim note so you know which field was found
            print(f"  {C.DIM}Customer.{CUSTOMER_PHONE_FIELD} detected as phone field{C.RESET}")

        if args.seed:
            print(f"\n{C.YELLOW}Seeding database...{C.RESET}")
            seed_db(db)

        # Ensure customer record exists
        customer = get_or_create_customer(db, phone)

        print_header(phone, role)

        turn_count = 0

        while True:
            # ── prompt ──
            try:
                raw = input(f"{C.BLUE}You ▶  {C.RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                print(f"\n{C.GRAY}Session ended.{C.RESET}\n")
                break

            if not raw:
                continue

            # ── commands ──
            if raw.startswith("/"):
                cmd = raw.lower().split()[0]
                arg = raw[len(cmd):].strip().lower()

                if cmd in ("/quit", "/exit"):
                    print(f"\n{C.GRAY}Goodbye. {turn_count} turn(s) in this session.{C.RESET}\n")
                    break

                elif cmd == "/reset":
                    customer = get_or_create_customer(db, phone)
                    turn_count = 0
                    print(f"  {C.AMBER}Session context cleared. Same phone, fresh conversation.{C.RESET}")

                elif cmd == "/history":
                    print_history(db, customer.id)

                elif cmd == "/tools":
                    print_tools(db, role)

                elif cmd == "/whoami":
                    db_phone = getattr(customer, CUSTOMER_PHONE_FIELD, "unknown")
                    print(
                        f"\n  {C.TEAL}Phone{C.RESET}  {phone}\n"
                        f"  {C.TEAL}Role {C.RESET}  {role}\n"
                        f"  {C.TEAL}DB ID{C.RESET}  customer#{customer.id}  "
                        f"({C.DIM}Customer.{CUSTOMER_PHONE_FIELD} = {db_phone}{C.RESET})\n"
                    )

                elif cmd == "/debug":
                    if arg in ("on", "1", "true"):
                        debug = True
                        print(f"  {C.LGREEN}Debug panel ON{C.RESET}")
                    elif arg in ("off", "0", "false"):
                        debug = False
                        print(f"  {C.AMBER}Debug panel OFF{C.RESET}")
                    else:
                        debug = not debug
                        print(f"  Debug panel {'ON' if debug else 'OFF'}")

                elif cmd == "/role":
                    if arg in ("owner", "customer"):
                        role = arg
                        print(f"  {C.AMBER}Switched to role: {role.upper()}{C.RESET}")
                    else:
                        print(f"  {C.RED}Unknown role '{arg}'. Use: owner | customer{C.RESET}")

                elif cmd == "/seed":
                    seed_db(db)

                elif cmd == "/clear":
                    os.system("cls" if os.name == "nt" else "clear")
                    print_header(phone, role)

                elif cmd == "/help":
                    print_help()

                else:
                    print(f"  {C.RED}Unknown command '{cmd}'. Type /help.{C.RESET}")

                continue

            # ── normal message ──
            turn_count += 1
            print_user_bubble(raw, phone)

            # show spinner while agent runs
            print(f"  {C.DIM}thinking…{C.RESET}", end="\r", flush=True)

            trace = await run_instrumented_turn(
                db=db,
                customer=customer,
                phone=phone,
                text=raw,
                role=role,
                debug=debug,
                verbose=args.verbose,
            )

            # clear spinner line
            print(" " * 20, end="\r")

            if trace.final_reply:
                print_agent_bubble(trace.final_reply, trace)

            if debug:
                print_debug_panel(trace, args.verbose)

    finally:
        db.close()


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Windows needs this for ANSI escape codes
    if sys.platform == "win32":
        os.system("color")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{C.GRAY}Interrupted.{C.RESET}\n")