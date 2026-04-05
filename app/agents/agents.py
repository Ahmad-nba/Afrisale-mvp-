import re
from typing import Any, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import prompt, tools
from app.core.config import settings
from app.memory.memory_service import format_memory_for_prompt, get_recent_messages
from app.models.models import Customer
from app.services import catalog as catalog_service
from app.services.catalog import search_products
from app.services.orders import create_order as create_order_service

# ===== STRUCTURES =====


class ToolCall(TypedDict):
    name: str
    args: Any


class TurnResult(TypedDict):
    intent: str
    input_type: str
    confidence: float
    state_before: str
    state_after: str
    tools_called: List[ToolCall]
    response: str


HARNESS_CUSTOMER_PHONE = "+19995550333"


def _ensure_customer_id(db: Session, state: dict) -> None:
    if state.get("customer_id"):
        return
    row = db.scalars(select(Customer).where(Customer.phone_number == HARNESS_CUSTOMER_PHONE)).first()
    if not row:
        row = Customer(phone_number=HARNESS_CUSTOMER_PHONE)
        db.add(row)
        db.commit()
        db.refresh(row)
    state["customer_id"] = row.id


# ===== INTENT DETECTION =====


def detect_intent(text: str, state: dict) -> tuple[str, str, float]:
    t = (text or "").strip()
    low = t.lower()

    if not t:
        return "unknown", "text", 0.4

    if low in ("hi", "hello", "hey"):
        return "greeting", "text", 0.95

    if any(k in low for k in ("order status", "my order", "track order")):
        return "order_followup", "text", 0.85

    if any(k in low for k in ("place order", "confirm order", "checkout")):
        return "place_order", "text", 0.88

    if state.get("current_state") == "selecting_product" and re.fullmatch(r"\d+", low):
        return "quantity_entry", "text", 0.9

    if state.get("last_products_shown") and re.fullmatch(r"\d+", low):
        return "product_pick", "text", 0.9

    if len(t) >= 2:
        return "product_search", "text", 0.75

    return "unknown", "text", 0.4


# ===== QUERY CLEANING =====


def extract_search_query(text: str) -> str:
    stop_phrases = ["what do you have", "show me", "i want", "do you have"]
    q = text.lower()
    for p in stop_phrases:
        q = q.replace(p, "")
    return q.strip()


# ===== MAIN ENGINE =====


def run_agent(user_input: str, session_state: dict, db: Session) -> TurnResult:
    tools_used: List[ToolCall] = []

    _ensure_customer_id(db, session_state)

    state_before = session_state["current_state"]

    intent, input_type, confidence = detect_intent(user_input, session_state)

    # ===== STATE TRANSITION =====
    if intent == "greeting":
        session_state["current_state"] = "idle"

    elif intent == "product_search":
        session_state["current_state"] = "browsing"

    elif intent == "order_followup":
        session_state["current_state"] = "idle"

    elif intent == "place_order":
        pass

    response_body = ""

    if intent == "greeting":
        response_body = "Welcome! What are you looking for today?"

    elif intent == "product_search":
        query = extract_search_query(user_input)

        tools_used.append(
            {
                "name": "search_products",
                "args": query,
            }
        )

        results = search_products(db, query)

        session_state["last_products_shown"] = results

        if not results:
            response_body = f'No products found for "{query}". Try another keyword.'
        else:
            lines = [
                f"{i + 1}. {p['title']} - {p['price']:,} UGX"
                for i, p in enumerate(results[:5])
            ]
            response_body = "Here are some options:\n" + "\n".join(lines)

    elif intent == "product_pick":
        try:
            idx = int(user_input.strip()) - 1
            selected = session_state["last_products_shown"][idx]
        except (ValueError, IndexError, TypeError):
            selected = None

        if not selected:
            response_body = "Invalid selection. Choose a valid number."
        else:
            session_state["selected_product"] = selected
            session_state["current_state"] = "selecting_product"

            response_body = f"You selected {selected['title']}. How many do you want?"

    elif intent == "quantity_entry":
        try:
            qty = int(user_input.strip())
        except ValueError:
            qty = 0

        if qty <= 0:
            response_body = "Enter a valid quantity."
        else:
            session_state["collected_order_fields"] = {
                "variant_id": session_state["selected_product"]["variant_id"],
                "quantity": qty,
            }
            session_state["current_state"] = "ordering"

            response_body = "Say 'place order' to confirm."

    elif intent == "place_order":
        fields = session_state.get("collected_order_fields", {})

        if fields and session_state.get("customer_id"):
            tools_used.append(
                {
                    "name": "save_order",
                    "args": dict(fields),
                }
            )

            msg = create_order_service(
                db,
                int(session_state["customer_id"]),
                int(fields["variant_id"]),
                int(fields["quantity"]),
            )
            response_body = msg

            session_state["current_state"] = "idle"
            session_state["selected_product"] = None
            session_state["last_products_shown"] = []
            session_state["collected_order_fields"] = {}
        else:
            response_body = "No order to place. Pick a product and quantity first."

    elif intent == "order_followup":
        response_body = "Order follow-up is not wired in this harness yet. Try product search."

    else:
        response_body = "I didn't understand. Try searching for a product."

    state_after = session_state["current_state"]

    return {
        "intent": intent,
        "input_type": input_type,
        "confidence": confidence,
        "state_before": state_before,
        "state_after": state_after,
        "tools_called": tools_used,
        "response": response_body,
    }


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def run_turn(db: Session, role: str, customer_id: int, user_text: str) -> str:
    """Single Gemini invoke + at most one tool (production path for SMS/WhatsApp)."""
    if not settings.google_api_key:
        return "Server misconfiguration: GOOGLE_API_KEY is not set."

    products_snapshot = catalog_service.get_products_formatted(db)
    memory_msgs = get_recent_messages(db, customer_id, limit=5)
    memory_block = format_memory_for_prompt(memory_msgs)
    system = prompt.build_system_prompt(role, products_snapshot, memory_block)
    tool_list = tools.build_owner_tools(db) if role == "owner" else tools.build_customer_tools(db, customer_id)

    model = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
    )
    model_with_tools = model.bind_tools(tool_list)
    messages = [SystemMessage(content=system), HumanMessage(content=user_text)]
    response = model_with_tools.invoke(messages)

    tool_calls = getattr(response, "tool_calls", None) or []
    if tool_calls:
        tc = tool_calls[0]
        name = tc.get("name")
        args = tc.get("args") or {}
        tool_map = {t.name: t for t in tool_list}
        chosen = tool_map.get(name)
        if not chosen:
            return "That action is not available."
        try:
            out = chosen.invoke(args)
        except Exception as exc:
            return f"Action failed: {exc}"
        return str(out)

    return _message_content_text(response.content)
