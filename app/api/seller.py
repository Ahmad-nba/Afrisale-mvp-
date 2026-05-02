"""
Seller-only HTTP API. All routes are gated by a single shared bearer token
defined as `SELLER_ACCESS_TOKEN` in the environment. The Next.js frontend
attaches it as `Authorization: Bearer <token>`.

Routes:
- GET  /api/seller/catalogue   list products with primary image + price + stock
- POST /api/seller/products    create a product (multipart/form-data, optional image)
- GET  /api/seller/orders      most-recent orders enriched with buyer + items

This is a single-seller MVP: there is no per-user identity check; possessing
the token authorizes every action.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.models import (
    Customer,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
)
from app.services import catalog, catalog_image_ingest, conversation_state_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/seller", tags=["seller"])

_bearer = HTTPBearer(auto_error=False)


def require_seller_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """
    Validates the shared seller token. Configuration mistakes (empty token in
    env) intentionally fail closed with 503 so a misconfigured deployment
    can't accidentally accept any token.
    """
    expected = (settings.seller_access_token or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Seller API is not configured.",
        )
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if (credentials.credentials or "").strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid seller token.",
        )
    return expected


def _stock_label(total: int) -> str:
    if total <= 0:
        return "out"
    if total <= 3:
        return "low"
    return "in"


@router.get("/catalogue")
def list_catalogue(
    db: Session = Depends(get_db),
    _: str = Depends(require_seller_token),
) -> list[dict[str, Any]]:
    """
    Returns the seller's full catalogue, one card per product.
    `price` is the minimum variant price (so cards never lie about price).
    `stock_total` and `stock_label` summarise availability across variants.
    """
    products = db.scalars(select(Product).order_by(Product.id)).all()
    rows: list[dict[str, Any]] = []
    for prod in products:
        variants = db.scalars(
            select(ProductVariant)
            .where(ProductVariant.product_id == prod.id)
            .order_by(ProductVariant.id)
        ).all()
        images = db.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == prod.id)
            .order_by(desc(ProductImage.is_primary), ProductImage.id)
        ).all()
        primary = images[0] if images else None
        prices = [v.price for v in variants if v.price]
        stock_total = sum(v.stock_quantity for v in variants)
        rows.append(
            {
                "id": prod.id,
                "name": prod.name,
                "description": prod.description or "",
                "price": min(prices) if prices else 0,
                "stock_total": stock_total,
                "stock_label": _stock_label(stock_total),
                "variants_count": len(variants),
                "image_url": primary.public_url if primary else "",
                "image_gcs_uri": primary.gcs_uri if primary else "",
            }
        )
    return rows


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    name: str = Form(...),
    price: int = Form(...),
    stock_quantity: int = Form(...),
    description: str = Form(""),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _: str = Depends(require_seller_token),
) -> dict[str, Any]:
    """
    Creates a product + initial variant, then optionally registers an image.
    Image registration uploads to GCS and embeds in-line so the new product
    is searchable immediately. Acceptable latency for the MVP because the
    seller is browser-side and expects a small wait after submit.
    """
    name_clean = (name or "").strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Name is required.")
    if price < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative.")
    if stock_quantity < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative.")

    catalog.add_product(db, name=name_clean, description=description or "")
    product = db.scalars(
        select(Product)
        .where(Product.name == name_clean)
        .order_by(desc(Product.id))
        .limit(1)
    ).first()
    if not product:
        raise HTTPException(status_code=500, detail="Product creation failed.")

    variant = db.scalars(
        select(ProductVariant)
        .where(ProductVariant.product_id == product.id)
        .order_by(ProductVariant.id)
        .limit(1)
    ).first()
    if not variant:
        raise HTTPException(status_code=500, detail="Initial variant missing.")

    catalog.update_price(db, variant_id=variant.id, price=int(price))
    catalog.update_stock(db, variant_id=variant.id, quantity=int(stock_quantity))

    image_payload: dict[str, Any] = {}
    if image is not None and (image.filename or image.size):
        try:
            image_bytes = await image.read()
        except Exception as exc:  # noqa: BLE001
            logger.exception("seller_upload_read_failed name=%s", name_clean)
            raise HTTPException(status_code=400, detail=f"Could not read image: {exc}")
        if image_bytes:
            mime = image.content_type or "image/jpeg"
            try:
                img_row = catalog_image_ingest.register_product_image(
                    db,
                    product_id=product.id,
                    image_bytes=image_bytes,
                    mime_type=mime,
                    is_primary=True,
                )
                image_payload = {
                    "image_id": img_row.id,
                    "image_url": img_row.public_url,
                    "image_gcs_uri": img_row.gcs_uri,
                }
            except Exception as exc:  # noqa: BLE001
                # Don't roll back the product on image failure: it's strictly
                # better to keep the catalogue row and let the seller retry
                # the image attachment via chat or a future re-upload route.
                logger.exception(
                    "seller_upload_image_failed product_id=%s name=%s",
                    product.id,
                    name_clean,
                )
                image_payload = {"image_error": str(exc)}

    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "variant_id": variant.id,
        "price": int(price),
        "stock_quantity": int(stock_quantity),
        **image_payload,
    }


@router.get("/orders")
def list_orders(
    limit: int = 50,
    db: Session = Depends(get_db),
    _: str = Depends(require_seller_token),
) -> list[dict[str, Any]]:
    """
    Returns recent orders newest-first. `delivery_location` is read from
    the customer's `ConversationState.deliveryLocation` because this MVP
    does not persist a location column on Order.
    """
    limit = max(1, min(int(limit or 50), 200))
    orders = db.scalars(select(Order).order_by(desc(Order.id)).limit(limit)).all()
    rows: list[dict[str, Any]] = []
    for order in orders:
        customer = db.get(Customer, order.customer_id)
        buyer_name = (customer.name or "").strip() if customer else ""
        phone = customer.phone_number if customer else ""
        delivery_location = ""
        if customer:
            try:
                state = conversation_state_service.get_state(db, customer.id)
                delivery_location = str(state.get("deliveryLocation") or "").strip()
            except Exception:
                delivery_location = ""
        items = db.scalars(
            select(OrderItem).where(OrderItem.order_id == order.id)
        ).all()
        item_payload: list[dict[str, Any]] = []
        for it in items:
            variant = db.get(ProductVariant, it.product_variant_id)
            product = db.get(Product, variant.product_id) if variant else None
            item_payload.append(
                {
                    "product_name": product.name if product else "",
                    "size": variant.size if variant else "",
                    "color": variant.color if variant else "",
                    "quantity": it.quantity,
                    "unit_price": variant.price if variant else 0,
                }
            )
        rows.append(
            {
                "id": order.id,
                "buyer_name": buyer_name or phone or "Anonymous",
                "phone": phone,
                "delivery_location": delivery_location,
                "items": item_payload,
                "total_price": order.total_price,
                "status": order.status,
            }
        )
    return rows
