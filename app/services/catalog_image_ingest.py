"""
Single source of truth for "register a new catalog image" used by both:
- the seed script that bulk-ingests existing assets
- the owner-side `add_product_image` tool (future WhatsApp-driven seller path)

Steps performed for each image:
  1. Upload original bytes to GCS under `catalog/<product_id>/<uuid>.<ext>`.
  2. Embed with Vertex AI multimodal embeddings (1408-dim).
  3. Upsert the vector into Vertex AI Vector Search.
  4. Persist a `ProductImage` row with the GCS URI and vector datapoint id.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import gcs
from app.models.models import Product, ProductImage
from app.services import embeddings, vector_search

logger = logging.getLogger(__name__)


def _ext_from_mime(mime: str) -> str:
    mime_low = (mime or "").lower()
    if "/" in mime_low:
        candidate = mime_low.split("/", 1)[1].split(";", 1)[0].strip()
        if candidate and candidate.replace("+", "").replace("-", "").isalnum():
            if candidate == "jpeg":
                return ".jpg"
            return "." + candidate
    return ".bin"


def _object_name(product_id: int, mime: str) -> str:
    return f"catalog/{int(product_id)}/{int(time.time())}_{uuid.uuid4().hex}{_ext_from_mime(mime)}"


def register_product_image(
    db: Session,
    product_id: int,
    image_bytes: bytes,
    mime_type: str,
    is_primary: Optional[bool] = None,
) -> ProductImage:
    """
    Persists a new image for `product_id`. If `is_primary` is None, the row
    becomes primary only if no other primary exists for this product.
    """
    product = db.get(Product, int(product_id))
    if not product:
        raise ValueError(f"Product {product_id} not found.")

    object_name = _object_name(product.id, mime_type)
    gcs_uri = gcs.upload_bytes(object_name, image_bytes, mime_type)
    public_url = gcs.public_https_url(gcs_uri)

    vector = embeddings.embed_image_gcs(gcs_uri)
    datapoint_id = vector_search.new_datapoint_id(prefix=f"prod{product.id}")
    vector_search.upsert_datapoint(
        datapoint_id=datapoint_id,
        vector=vector,
        restricts=[{"namespace": "kind", "allow_list": ["product_image"]}],
    )

    if is_primary is None:
        existing_primary = db.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == product.id)
            .where(ProductImage.is_primary.is_(True))
        ).first()
        is_primary = existing_primary is None

    image = ProductImage(
        product_id=product.id,
        gcs_uri=gcs_uri,
        public_url=public_url,
        mime_type=mime_type or "image/jpeg",
        is_primary=bool(is_primary),
        vector_datapoint_id=datapoint_id,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    logger.info(
        "catalog_image_registered product_id=%s image_id=%s datapoint=%s",
        product.id,
        image.id,
        datapoint_id,
    )
    return image


def register_product_image_from_attachment(
    db: Session,
    product_id: int,
    attachment_id: int,
    is_primary: Optional[bool] = None,
) -> ProductImage:
    """
    Used by the owner WhatsApp upload path: take an inbound attachment we
    already archived to GCS and re-use it as a catalog image (re-embedding
    via gcs_uri so we don't re-download).
    """
    from app.models.models import MessageAttachment

    attachment = db.get(MessageAttachment, int(attachment_id))
    if not attachment or not attachment.gcs_uri:
        raise ValueError(f"Attachment {attachment_id} not found or missing gcs_uri.")

    product = db.get(Product, int(product_id))
    if not product:
        raise ValueError(f"Product {product_id} not found.")

    vector = embeddings.embed_image_gcs(attachment.gcs_uri)
    datapoint_id = vector_search.new_datapoint_id(prefix=f"prod{product.id}")
    vector_search.upsert_datapoint(
        datapoint_id=datapoint_id,
        vector=vector,
        restricts=[{"namespace": "kind", "allow_list": ["product_image"]}],
    )

    if is_primary is None:
        existing_primary = db.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == product.id)
            .where(ProductImage.is_primary.is_(True))
        ).first()
        is_primary = existing_primary is None

    image = ProductImage(
        product_id=product.id,
        gcs_uri=attachment.gcs_uri,
        public_url=attachment.public_url or "",
        mime_type=attachment.mime_type or "image/jpeg",
        is_primary=bool(is_primary),
        vector_datapoint_id=datapoint_id,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    logger.info(
        "catalog_image_registered_from_attachment product_id=%s image_id=%s",
        product.id,
        image.id,
    )
    return image
