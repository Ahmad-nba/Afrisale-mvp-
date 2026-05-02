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
    # Best-effort enqueue for the seller batched-notification loop. Imported
    # lazily to avoid a circular import with the notification module which
    # itself imports from app.models.
    try:
        from app.services import seller_notification

        seller_notification.queue_order_notification(db, order.id)
    except Exception:
        # Notification is non-critical; never break order creation on failure.
        pass
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
