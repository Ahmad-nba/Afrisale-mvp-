"""
High-level catalog matching by image or by text.

Both flows embed the query into the same multimodal vector space, query
Vertex AI Vector Search for nearest neighbors, then resolve neighbor IDs
to `ProductImage -> Product -> ProductVariant` rows.

Returns a list of structured matches the agent (and the outbound dispatch
stage) can consume to compose WhatsApp media cards.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations import gcs
from app.models.models import MessageAttachment, Product, ProductImage, ProductVariant
from app.services import embeddings, vector_search

logger = logging.getLogger(__name__)


def _resolve_match(db: Session, datapoint_id: str, similarity: float, distance: float) -> Optional[dict[str, Any]]:
    image = db.scalars(
        select(ProductImage).where(ProductImage.vector_datapoint_id == datapoint_id)
    ).first()
    if not image:
        return None
    product = db.get(Product, image.product_id)
    if not product:
        return None
    variants = db.scalars(
        select(ProductVariant)
        .where(ProductVariant.product_id == product.id)
        .order_by(ProductVariant.id)
    ).all()
    variant_payload = [
        {
            "variant_id": v.id,
            "size": v.size,
            "color": v.color,
            "price": int(v.price or 0),
            "stock_quantity": int(v.stock_quantity or 0),
        }
        for v in variants
    ]
    public_url = image.public_url
    if not public_url and image.gcs_uri:
        try:
            public_url = gcs.public_https_url(image.gcs_uri)
        except Exception:
            public_url = ""

    return {
        "product_id": int(product.id),
        "name": product.name,
        "description": product.description or "",
        "image_url": public_url,
        "image_gcs_uri": image.gcs_uri,
        "variants": variant_payload,
        "similarity": float(similarity),
        "distance": float(distance),
    }


def _dedupe_top_per_product(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the strongest neighbor per product so we don't repeat cards."""
    seen: dict[int, dict[str, Any]] = {}
    for match in matches:
        pid = int(match.get("product_id") or 0)
        if pid <= 0:
            continue
        existing = seen.get(pid)
        if existing is None or match.get("similarity", 0.0) > existing.get("similarity", 0.0):
            seen[pid] = match
    out = list(seen.values())
    out.sort(key=lambda m: float(m.get("similarity", 0.0)), reverse=True)
    return out


def _filter_by_threshold(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    threshold = float(settings.image_match_min_similarity or 0.0)
    if threshold <= 0:
        return matches
    return [m for m in matches if float(m.get("similarity", 0.0)) >= threshold]


def search_by_vector(
    db: Session,
    vector: list[float],
    top_k: Optional[int] = None,
) -> list[dict[str, Any]]:
    k = int(top_k or settings.image_match_top_k or 4)
    fetch_k = max(k * 2, 6)
    neighbors = vector_search.find_neighbors(vector=vector, top_k=fetch_k)
    matches: list[dict[str, Any]] = []
    for neighbor in neighbors:
        resolved = _resolve_match(
            db,
            datapoint_id=neighbor.datapoint_id,
            similarity=neighbor.similarity,
            distance=neighbor.distance,
        )
        if resolved:
            matches.append(resolved)
    matches = _dedupe_top_per_product(matches)
    matches = _filter_by_threshold(matches)
    return matches[:k]


def search_by_image_attachment(
    db: Session,
    attachment_id: int,
    top_k: Optional[int] = None,
) -> list[dict[str, Any]]:
    attachment = db.get(MessageAttachment, int(attachment_id))
    if not attachment:
        logger.warning("image_search attachment_not_found id=%s", attachment_id)
        return []
    if not attachment.gcs_uri:
        logger.warning("image_search attachment_missing_gcs id=%s", attachment_id)
        return []
    try:
        vector = embeddings.embed_image_gcs(attachment.gcs_uri)
    except Exception:
        logger.exception("image_search embed_failed id=%s", attachment_id)
        return []
    return search_by_vector(db, vector=vector, top_k=top_k)


def search_by_image_bytes(
    db: Session,
    image_bytes: bytes,
    mime_type: Optional[str] = None,
    top_k: Optional[int] = None,
) -> list[dict[str, Any]]:
    try:
        vector = embeddings.embed_image_bytes(image_bytes, mime_type=mime_type)
    except Exception:
        logger.exception("image_search embed_bytes_failed")
        return []
    return search_by_vector(db, vector=vector, top_k=top_k)


def search_by_text(
    db: Session,
    query: str,
    top_k: Optional[int] = None,
) -> list[dict[str, Any]]:
    text = (query or "").strip()
    if not text:
        return []
    try:
        vector = embeddings.embed_text(text)
    except Exception:
        logger.exception("image_search embed_text_failed query=%s", text[:80])
        return []
    return search_by_vector(db, vector=vector, top_k=top_k)
