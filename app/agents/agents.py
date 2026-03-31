from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents import prompt, tools
from app.core.config import settings
from app.memory.memory_service import format_memory_for_prompt, get_recent_messages
from app.services import catalog
from sqlalchemy.orm import Session


def _message_content_text(content) -> str:
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
    if not settings.google_api_key:
        return "Server misconfiguration: GOOGLE_API_KEY is not set."

    products_snapshot = catalog.get_products_formatted(db)
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
