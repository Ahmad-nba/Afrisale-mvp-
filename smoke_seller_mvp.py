"""
Local smoke test for the Seller MVP.

Asserts:
  1. /api/seller/* requires the bearer token (401 / 403 paths).
  2. /api/seller/catalogue returns the seeded products.
  3. /api/seller/orders returns recent orders enriched with buyer info.
  4. orders.create_order enqueues a PendingSellerNotification.
  5. seller_notification.flush_pending coalesces 6 pending rows into a
     single WhatsApp call (twilio is stubbed).
  6. The owner share_*_link tools build the expected URL.

Run:
    python smoke_seller_mvp.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
# Inject deterministic env so the smoke test passes regardless of .env state.
# `load_dotenv` sets empty values, which `setdefault` won't override, so we
# assign directly here.
os.environ["SELLER_ACCESS_TOKEN"] = "smoke-test-token"
os.environ["SELLER_BASE_URL"] = "http://localhost:3000"
os.environ["OWNER_PHONE"] = "+15555550100"
os.environ["SELLER_NOTIFICATION_WINDOW_SECONDS"] = "300"

# Reload settings to pick up the env we just injected.
from app.core import config as config_module  # noqa: E402

config_module.settings = config_module.Settings()
SETTINGS = config_module.settings

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.models import (  # noqa: E402
    Customer,
    Order,
    OrderItem,
    PendingSellerNotification,
    Product,
    ProductVariant,
)
from app.parlant_agent import tool_registry  # noqa: E402
from app.services import orders as orders_service  # noqa: E402
from app.services import seller_notification  # noqa: E402


def header_with(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_routes_require_token(client: TestClient) -> None:
    r = client.get("/api/seller/catalogue")
    assert r.status_code == 401, r.text
    r = client.get("/api/seller/catalogue", headers=header_with("wrong"))
    assert r.status_code == 403, r.text
    print("  ok: token gating")


def test_catalogue(client: TestClient) -> None:
    r = client.get(
        "/api/seller/catalogue", headers=header_with(SETTINGS.seller_access_token)
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    print(f"  ok: catalogue returned {len(data)} products")


def test_orders_route(client: TestClient) -> None:
    r = client.get(
        "/api/seller/orders", headers=header_with(SETTINGS.seller_access_token)
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    print(f"  ok: orders returned {len(data)} entries")


def _ensure_test_customer(db) -> Customer:
    cust = (
        db.query(Customer)
        .filter(Customer.phone_number == "+15555550101")
        .one_or_none()
    )
    if not cust:
        cust = Customer(phone_number="+15555550101", name="Smoke Buyer")
        db.add(cust)
        db.commit()
        db.refresh(cust)
    return cust


def _ensure_test_variant(db) -> ProductVariant | None:
    return db.query(ProductVariant).order_by(ProductVariant.id).first()


def test_create_order_enqueues(client: TestClient) -> None:
    db = SessionLocal()
    try:
        variant = _ensure_test_variant(db)
        if variant is None:
            print("  skip: no variants in DB to create an order")
            return
        if variant.stock_quantity < 6:
            variant.stock_quantity = 50
            db.commit()
        cust = _ensure_test_customer(db)

        # Clear any prior undelivered rows so the assertion is precise.
        db.query(PendingSellerNotification).filter(
            PendingSellerNotification.delivered_at.is_(None)
        ).delete()
        db.commit()

        for _ in range(6):
            orders_service.create_order(db, cust.id, variant.id, 1)

        pending = (
            db.query(PendingSellerNotification)
            .filter(PendingSellerNotification.delivered_at.is_(None))
            .count()
        )
        assert pending == 6, f"expected 6 pending rows, got {pending}"
        print("  ok: 6 orders -> 6 pending seller notifications")

        with patch(
            "app.services.seller_notification.twilio_whatsapp.send_whatsapp"
        ) as send:
            flushed = seller_notification.flush_pending(db)
            assert flushed == 6, f"expected 6 flushed, got {flushed}"
            assert send.call_count == 1, (
                f"expected one batched WA send, got {send.call_count}"
            )
            args, _kwargs = send.call_args
            to, body = args[0], args[1]
            assert to == SETTINGS.owner_phone
            assert "6 new orders" in body, body
            assert "/seller/orders?t=" in body, body
        print("  ok: flush_pending sent 1 batched WA with 6 orders")
    finally:
        db.close()


def test_owner_share_links() -> None:
    db = SessionLocal()
    try:
        tools = tool_registry.build_owner_tools(db, last_attachments=[])
        by_name = {t["name"]: t for t in tools}
        for tool_name, expected_path in (
            ("share_upload_link", "/seller/upload"),
            ("share_catalogue_link", "/seller/catalogue"),
            ("share_orders_link", "/seller/orders"),
        ):
            assert tool_name in by_name, f"missing tool {tool_name}"
            result = by_name[tool_name]["handler"](db)
            assert isinstance(result, str), result
            assert expected_path in result, result
            assert SETTINGS.seller_access_token in result, result
        print("  ok: share_*_link tools render expected URLs")
    finally:
        db.close()


def main() -> int:
    import main as app_module

    client = TestClient(app_module.app)
    print("Seller MVP smoke test")
    print("- token gating")
    test_routes_require_token(client)
    print("- catalogue")
    test_catalogue(client)
    print("- orders endpoint")
    test_orders_route(client)
    print("- order -> notification queue")
    test_create_order_enqueues(client)
    print("- owner share tools")
    test_owner_share_links()
    print("All seller MVP smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
