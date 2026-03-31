import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/services/__init__.py", "")
w("app/services/catalog.py", r"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Order, OrderItem, Product, ProductVariant


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

from app.models.models import Customer, Order, OrderItem, ProductVariant


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
        if pv and pv.product:
            pname = pv.product.name
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
print("services")
