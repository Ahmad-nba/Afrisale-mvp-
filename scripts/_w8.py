import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/agents/__init__.py", "")
w("app/agents/prompt.py", r"""
def build_system_prompt(role: str, products_snapshot: str, memory_block: str) -> str:
    if role == "owner":
        return (
            "You are assisting the shop owner.\n"
            "You MUST call a tool for every management action.\n"
            "Never confirm a change without calling the corresponding tool.\n"
            f"Available products snapshot:\n{products_snapshot}\n"
            f"Conversation history:\n{memory_block}\n"
        )
    return (
        "You are a sales assistant for a clothing store.\n"
        "You ONLY sell products listed below.\n"
        "To the customer, you must have a friendly tone, a welcoming tone, take it like the customer has entered a shop "
        "and is inquiring about a product. You MUST ask questions to clarify size, color, and delivery location before "
        "confirming an order.\n"
        "Your goal is to ensure you close sale and eliminate customer turndown.\n"
        "To the owner you are a helpful assistant that helps them manage their shop. You help them know, update, "
        "understand their store.\n"
        "You MUST call a tool to take any action.\n"
        "Never confirm an order without calling create_order().\n"
        f"Available products:\n{products_snapshot}\n"
        f"Conversation history:\n{memory_block}\n"
    )
""")

w("app/agents/tools.py", r"""
from sqlalchemy.orm import Session
from langchain_core.tools import StructuredTool

from app.services import catalog, orders


def build_customer_tools(db: Session, customer_id: int) -> list[StructuredTool]:
    def get_products() -> str:
        return catalog.get_products_formatted(db)

    def create_order(product_variant_id: int, quantity: int) -> str:
        return orders.create_order(db, customer_id, product_variant_id, quantity)

    def check_order_status(order_id: int) -> str:
        return orders.check_order_status(db, customer_id, order_id)

    return [
        StructuredTool.from_function(
            get_products,
            name="get_products",
            description="List all products and variants with ids, sizes, colors, prices, and stock.",
        ),
        StructuredTool.from_function(
            create_order,
            name="create_order",
            description="Create an order for the current customer. Args: product_variant_id, quantity.",
        ),
        StructuredTool.from_function(
            check_order_status,
            name="check_order_status",
            description="Show status and line items for an order id for this customer.",
        ),
    ]


def build_owner_tools(db: Session) -> list[StructuredTool]:
    def add_product(name: str, description: str) -> str:
        return catalog.add_product(db, name, description)

    def update_stock(variant_id: int, quantity: int) -> str:
        return catalog.update_stock(db, variant_id, quantity)

    def update_price(variant_id: int, price: int) -> str:
        return catalog.update_price(db, variant_id, price)

    def view_orders() -> str:
        return orders.view_orders(db)

    return [
        StructuredTool.from_function(
            add_product,
            name="add_product",
            description="Add a new product with name and description. Creates a default variant to set price/stock later.",
        ),
        StructuredTool.from_function(
            update_stock,
            name="update_stock",
            description="Set stock quantity for a product variant id.",
        ),
        StructuredTool.from_function(
            update_price,
            name="update_price",
            description="Set price (integer) for a product variant id.",
        ),
        StructuredTool.from_function(
            view_orders,
            name="view_orders",
            description="List recent orders with customer phone and totals.",
        ),
    ]
""")

w("app/agents/agents.py", r"""
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
""")
print("agents")
