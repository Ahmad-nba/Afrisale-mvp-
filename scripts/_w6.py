import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/memory/memory_service.py", r"""
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.models import Message


def get_recent_messages(db: Session, customer_id: int, limit: int = 5) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.customer_id == customer_id)
        .order_by(desc(Message.id))
        .limit(limit)
    )
    rows = list(db.scalars(stmt).all())
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

w("app/services/catalog.py", r"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Product, ProductVariant


def get_products_formatted(db: Session) -> str:
    products = db.scalars(select(Product).order_by(Product.id)).all()
    if not products:
        return "No products in catalog yet."
    parts: list[str] = []
    for p in products:
        parts.append(f"- {p.name}: {p.description or 'No description'}")
        variants = db.scalars(
            select(ProductVariant).where(ProductVariant.product_id == p.id).order_by(ProductVariant.id)
        ).all()
        for v in variants:
            parts.append(
                f"  * Variant #{v.id} | size={v.size} | color={v.color} | price={v.price} | stock={v.stock_quantity}"
            )
    return "\n".join(parts)


def add_product(db: Session, name: str, description: str) -> str:
    p = Product(name=name.strip(), description=(description or "").strip())
    db.add(p)
    db.flush()
    v = ProductVariant(
        product_id=p.id,
        size="Standard",
        color="Default",
        price=0,
        stock_quantity=0,
    )
    db.add(v)
    db.commit()
    return f"Product added (id={p.id}) with initial variant id={v.id}. Use update_price and update_stock to set catalog details."


def update_stock(db: Session, variant_id: int, quantity: int) -> str:
    v = db.get(ProductVariant, variant_id)
    if not v:
        return "Variant not found."
    v.stock_quantity = int(quantity)
    db.commit()
    return f"Stock for variant {variant_id} set to {v.stock_quantity}."


def update_price(db: Session, variant_id: int, price: int) -> str:
    v = db.get(ProductVariant, variant_id)
    if not v:
        return "Variant not found."
    v.price = int(price)
    db.commit()
    return f"Price for variant {variant_id} set to {v.price}."
""")

w("app/services/orders.py", r"""
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.models import Customer, Order, OrderItem, Product, ProductVariant


def create_order(db: Session, customer_id: int, product_variant_id: int, quantity: int) -> str:
    if quantity < 1:
        return "Quantity must be at least 1."
    v = db.get(ProductVariant, product_variant_id)
    if not v:
        return "Product variant not found."
    if v.stock_quantity < quantity:
        return f"Not enough stock. Available: {v.stock_quantity}."

    line_total = v.price * quantity
    order = Order(customer_id=customer_id, status="pending", total_price=line_total)
    db.add(order)
    db.flush()
    item = OrderItem(order_id=order.id, product_variant_id=product_variant_id, quantity=quantity)
    db.add(item)
    v.stock_quantity -= quantity
    db.commit()
    return f"Order created: id={order.id}, total={line_total}, status=pending."


def check_order_status(db: Session, customer_id: int, order_id: int) -> str:
    order = db.get(Order, order_id)
    if not order:
        return "Order not found."
    if order.customer_id != customer_id:
        return "You cannot view this order."
    items = db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    lines = [f"Order {order.id}: status={order.status}, total={order.total_price}"]
    for it in items:
        pv = db.get(ProductVariant, it.product_variant_id)
        pname = ""
        if pv:
            prod = db.get(Product, pv.product_id)
            pname = prod.name if prod else ""
        lines.append(f"  - variant {it.product_variant_id} ({pname}) x{it.quantity}")
    return "\n".join(lines)


def view_orders(db: Session, limit: int = 20) -> str:
    orders = db.scalars(select(Order).order_by(desc(Order.id)).limit(limit)).all()
    if not orders:
        return "No orders yet."
    parts: list[str] = []
    for o in orders:
        cust = db.get(Customer, o.customer_id)
        phone = cust.phone_number if cust else "?"
        parts.append(f"Order {o.id} | customer {o.customer_id} ({phone}) | {o.status} | total={o.total_price}")
    return "\n".join(parts)
""")

w("app/guardrails/output_guardrails.py", r"""
import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Product, ProductVariant

_FALLBACK = (
    "I can only share information that matches our catalog. Ask for our product list or clarify size and color."
)


def load_catalog_hints(db: Session) -> tuple[set[str], set[int]]:
    names = {p.name.lower() for p in db.scalars(select(Product)).all()}
    prices = set(db.scalars(select(ProductVariant.price)).all())
    return names, prices


def validate_assistant_text(db: Session, text: str | None) -> str:
    if text is None:
        return _FALLBACK
    s = str(text).strip()
    if not s:
        return _FALLBACK
    names, prices = load_catalog_hints(db)
    low = s.lower()
    for m in re.finditer(r"(?i)\b(ugx|kes|usd|rwf|tzs)\s*[:\s]*([\d,]+)\b", s):
        val = int(m.group(2).replace(",", ""))
        if val not in prices:
            return _FALLBACK
    for m in re.finditer(r"\b\d+\b", s):
        val = int(m.group(0))
        if val in prices:
            continue
        window = s[max(0, m.start() - 16) : m.end() + 16].lower()
        if any(k in window for k in ("ugx", "kes", "usd", "rwf", "tzs", "price", "cost", "shilling")):
            return _FALLBACK
    if names:
        for m in re.finditer(r"\b([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{3,})*)\b", s):
            phrase = m.group(1)
            pl = phrase.lower()
            if pl in ("assistant", "standard", "default", "order", "status", "pending", "thanks", "hello"):
                continue
            if not any(pl in n or n in pl for n in names if len(n) >= 3):
                return _FALLBACK
    return s
""")

w("app/integrations/__init__.py", "")
w("app/integrations/africastalking.py", r"""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_sms(to: str, message: str) -> None:
    if settings.skip_sms_send:
        logger.info("skip_sms_send: would send to %s: %s", to, message[:120])
        return
    if not settings.at_username or not settings.at_api_key:
        logger.warning("Africa's Talking credentials missing; SMS not sent.")
        return
    payload = {
        "username": settings.at_username,
        "to": to,
        "message": message,
    }
    if settings.at_sender_id:
        payload["from"] = settings.at_sender_id
    headers = {
        "apiKey": settings.at_api_key,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(settings.at_base_url, data=payload, headers=headers)
        if r.status_code >= 400:
            logger.error("Africa's Talking error %s: %s", r.status_code, r.text[:500])
    except Exception:
        logger.exception("Failed to send SMS")
""")
print("patch1")
