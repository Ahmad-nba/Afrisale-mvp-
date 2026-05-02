"""
Seller order notifications: DB-backed queue + debounced batched WhatsApp send.

Why DB-backed: an in-process timer would drop pending notifications on app
restart. By writing each new order into `pending_seller_notifications`, we
keep a durable queue that the flush loop drains every
`SELLER_NOTIFICATION_WINDOW_SECONDS` (default 300).

Lifecycle:
- `queue_order_notification(db, order_id)` is called from `orders.create_order`
  right after a successful commit. Inserts an undelivered row.
- `flush_pending(db)` selects all undelivered rows, builds a single message
  body, sends one WA to OWNER_PHONE, then stamps `delivered_at` on each.
- `start_background_loop(loop)` schedules the periodic flush.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.integrations import twilio_whatsapp
from app.models.models import (
    Customer,
    Order,
    OrderItem,
    PendingSellerNotification,
    Product,
    ProductVariant,
)

logger = logging.getLogger(__name__)


def _orders_link() -> str:
    base = (settings.seller_base_url or "").rstrip("/")
    token = settings.seller_access_token or ""
    if not base:
        return ""
    if token:
        return f"{base}/seller/orders?t={token}"
    return f"{base}/seller/orders"


def queue_order_notification(db: Session, order_id: int) -> None:
    """Idempotent enqueue. Safe to call from inside the order transaction."""
    try:
        existing = db.scalars(
            select(PendingSellerNotification).where(
                PendingSellerNotification.order_id == int(order_id)
            )
        ).first()
        if existing:
            return
        row = PendingSellerNotification(order_id=int(order_id))
        db.add(row)
        db.commit()
        logger.info("seller_notification_queued order_id=%s", order_id)
    except Exception:
        logger.exception("seller_notification_queue_failed order_id=%s", order_id)
        try:
            db.rollback()
        except Exception:
            pass


def _summarize_order(db: Session, order_id: int) -> dict[str, Any]:
    order = db.get(Order, int(order_id))
    if not order:
        return {"id": order_id, "buyer": "?", "phone": "?", "total": 0}
    customer = db.get(Customer, order.customer_id)
    buyer = (customer.name or "").strip() if customer else ""
    if not buyer and customer:
        buyer = customer.phone_number
    items = db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all()
    item_lines: list[str] = []
    for it in items:
        variant = db.get(ProductVariant, it.product_variant_id)
        product = db.get(Product, variant.product_id) if variant else None
        item_lines.append(
            f"{(product.name if product else 'product')} x{it.quantity}"
        )
    return {
        "id": order.id,
        "buyer": buyer or "Anonymous",
        "phone": customer.phone_number if customer else "?",
        "total": int(order.total_price or 0),
        "items": ", ".join(item_lines),
    }


def _build_body(orders: list[dict[str, Any]]) -> str:
    link = _orders_link()
    if len(orders) == 1:
        o = orders[0]
        head = (
            f"New order #{o['id']} from {o['buyer']} ({o['phone']}). "
            f"Total: {o['total']:,}."
        )
        if o.get("items"):
            head += f"\nItems: {o['items']}"
        if link:
            head += f"\nView: {link}"
        return head
    head = f"You have {len(orders)} new orders."
    bullets = "\n".join(
        f"- #{o['id']} {o['buyer']} - {o['total']:,}" for o in orders
    )
    if link:
        return f"{head}\n{bullets}\nView: {link}"
    return f"{head}\n{bullets}"


def flush_pending(db: Session) -> int:
    """
    Sends a single batched WhatsApp message for all undelivered rows and
    marks them as delivered. Returns the number of orders flushed.
    """
    seller_phone = (settings.owner_phone or "").strip()
    if not seller_phone:
        logger.debug("seller_notification_skip reason=no_owner_phone")
        return 0

    rows = db.scalars(
        select(PendingSellerNotification).where(
            PendingSellerNotification.delivered_at.is_(None)
        )
    ).all()
    if not rows:
        return 0

    summaries = [_summarize_order(db, row.order_id) for row in rows]
    summaries.sort(key=lambda s: int(s.get("id") or 0))
    body = _build_body(summaries)

    try:
        twilio_whatsapp.send_whatsapp(seller_phone, body)
    except Exception:
        logger.exception("seller_notification_send_failed count=%d", len(rows))
        return 0

    now = datetime.utcnow()
    for row in rows:
        row.delivered_at = now
    db.commit()
    logger.info("seller_notification_flushed count=%d", len(rows))
    return len(rows)


async def _periodic_flush_loop() -> None:
    interval = max(5, int(settings.seller_notification_window_seconds or 300))
    logger.info("seller_notification_loop_started interval=%ds", interval)
    while True:
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("seller_notification_loop_cancelled")
            return
        db = SessionLocal()
        try:
            flush_pending(db)
        except Exception:
            logger.exception("seller_notification_loop_iteration_failed")
        finally:
            try:
                db.close()
            except Exception:
                pass


def start_background_loop() -> asyncio.Task:
    """
    Schedules the periodic flush on the running event loop. Caller is
    responsible for cancelling the returned task on shutdown.
    """
    return asyncio.create_task(_periodic_flush_loop(), name="seller_notification_loop")
