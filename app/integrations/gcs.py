"""
Google Cloud Storage helpers.

Used for:
- archiving inbound user media (so we keep durable copies even after Twilio's short-lived URLs expire)
- hosting catalog product images that we send back as WhatsApp media cards
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client():
    """
    Lazy import keeps the module loadable in environments where the storage
    package is not installed (e.g., test runners that monkeypatch this layer).
    """
    from google.cloud import storage

    return storage.Client(project=settings.gcp_project_id or None)


def _bucket(name: Optional[str] = None):
    bucket_name = (name or settings.gcs_bucket_products or "").strip()
    if not bucket_name:
        raise ValueError("GCS_BUCKET_PRODUCTS is not configured.")
    return _client().bucket(bucket_name)


def upload_bytes(
    object_name: str,
    data: bytes,
    mime_type: str,
    bucket_name: Optional[str] = None,
) -> str:
    """
    Uploads raw bytes to GCS. Returns the gs:// URI.
    """
    bucket = _bucket(bucket_name)
    blob = bucket.blob(object_name)
    blob.upload_from_string(data, content_type=mime_type or "application/octet-stream")
    uri = f"gs://{bucket.name}/{object_name}"
    logger.info("gcs_upload ok object=%s bytes=%d", object_name, len(data))
    return uri


def public_https_url(gcs_uri: str) -> str:
    """
    Returns an https URL for a gs:// URI assuming the bucket grants public
    read or the object is otherwise reachable. Falls back to a signed URL
    when not public.
    """
    if not gcs_uri.startswith("gs://"):
        return gcs_uri
    rest = gcs_uri[len("gs://"):]
    if "/" not in rest:
        return gcs_uri
    bucket_name, object_name = rest.split("/", 1)
    return f"https://storage.googleapis.com/{bucket_name}/{object_name}"


def signed_url(
    gcs_uri: str,
    ttl_seconds: Optional[int] = None,
    method: str = "GET",
) -> str:
    """
    Builds a v4 signed URL for the given gs:// URI.
    Required when bucket is private (Twilio still needs to fetch it).
    """
    if not gcs_uri.startswith("gs://"):
        return gcs_uri
    rest = gcs_uri[len("gs://"):]
    if "/" not in rest:
        raise ValueError(f"Malformed gcs_uri: {gcs_uri}")
    bucket_name, object_name = rest.split("/", 1)
    bucket = _bucket(bucket_name)
    blob = bucket.blob(object_name)
    expiration = timedelta(seconds=int(ttl_seconds or settings.gcs_signed_url_ttl_seconds))
    return blob.generate_signed_url(expiration=expiration, method=method, version="v4")


def delete_object(gcs_uri: str) -> None:
    if not gcs_uri.startswith("gs://"):
        return
    rest = gcs_uri[len("gs://"):]
    if "/" not in rest:
        return
    bucket_name, object_name = rest.split("/", 1)
    bucket = _bucket(bucket_name)
    try:
        bucket.blob(object_name).delete()
    except Exception:
        logger.exception("gcs_delete_failed object=%s", object_name)
