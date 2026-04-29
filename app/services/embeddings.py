"""
Vertex AI multimodal embedding wrappers.

Both images and text are embedded into the same 1408-dim vector space using
`multimodalembedding@001`, which lets us match user-supplied images to
catalog images AND user-supplied text descriptions ("air jordans") to the
same set of catalog datapoints.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _ensure_credentials_env() -> None:
    """
    Pydantic-settings reads GOOGLE_APPLICATION_CREDENTIALS from .env, but
    the underlying google.auth client only inspects the actual process env.
    Mirror the value so ADC works regardless of how the app was launched.
    """
    cp = (settings.google_application_credentials or "").strip()
    if cp and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cp


def _init_vertex() -> None:
    from google.cloud import aiplatform

    _ensure_credentials_env()
    project = (settings.gcp_project_id or "").strip()
    location = (settings.gcp_location or "us-central1").strip()
    if not project:
        raise EnvironmentError("GCP_PROJECT_ID must be set for embeddings.")
    aiplatform.init(project=project, location=location)


def _embedding_model():
    from vertexai.vision_models import MultiModalEmbeddingModel

    _init_vertex()
    model_name = (settings.vertex_embedding_model or "multimodalembedding@001").strip()
    return MultiModalEmbeddingModel.from_pretrained(model_name)


def embed_image_bytes(image_bytes: bytes, mime_type: str | None = None) -> list[float]:
    """
    Embeds raw image bytes. Used for inbound user images where we already
    have the binary in memory.
    """
    from vertexai.vision_models import Image

    model = _embedding_model()
    image = Image(image_bytes=image_bytes)
    embeddings = model.get_embeddings(
        image=image,
        dimension=int(settings.vertex_vector_dimensions or 1408),
    )
    vector = list(embeddings.image_embedding or [])
    if not vector:
        raise RuntimeError("Vertex AI returned an empty image embedding.")
    return [float(v) for v in vector]


def embed_image_gcs(gcs_uri: str) -> list[float]:
    """
    Embeds an image referenced by a gs:// URI. Used during catalog ingestion.
    """
    from vertexai.vision_models import Image

    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"embed_image_gcs requires gs:// URI, got: {gcs_uri}")
    model = _embedding_model()
    image = Image(gcs_uri=gcs_uri)
    embeddings = model.get_embeddings(
        image=image,
        dimension=int(settings.vertex_vector_dimensions or 1408),
    )
    vector = list(embeddings.image_embedding or [])
    if not vector:
        raise RuntimeError(f"Vertex AI returned an empty image embedding for {gcs_uri}.")
    return [float(v) for v in vector]


def embed_text(text: str) -> list[float]:
    """
    Embeds text into the same multimodal space as images, so we can use
    catalog text descriptions or user text queries against image vectors.
    """
    if not (text or "").strip():
        raise ValueError("embed_text requires non-empty text.")
    model = _embedding_model()
    embeddings = model.get_embeddings(
        contextual_text=text,
        dimension=int(settings.vertex_vector_dimensions or 1408),
    )
    vector = list(embeddings.text_embedding or [])
    if not vector:
        raise RuntimeError("Vertex AI returned an empty text embedding.")
    return [float(v) for v in vector]


def embed_image_and_text(
    image_bytes: Optional[bytes] = None,
    image_gcs_uri: Optional[str] = None,
    text: Optional[str] = None,
) -> dict[str, list[float]]:
    """
    Convenience helper that returns whichever vectors are requested in one call,
    avoiding multiple model loads. Returns dict with optional 'image'/'text' keys.
    """
    from vertexai.vision_models import Image

    if not image_bytes and not image_gcs_uri and not (text or "").strip():
        raise ValueError("Need at least one of image_bytes, image_gcs_uri, or text.")

    model = _embedding_model()
    image = None
    if image_bytes:
        image = Image(image_bytes=image_bytes)
    elif image_gcs_uri:
        if not image_gcs_uri.startswith("gs://"):
            raise ValueError(f"image_gcs_uri must start with gs://, got: {image_gcs_uri}")
        image = Image(gcs_uri=image_gcs_uri)

    embeddings = model.get_embeddings(
        image=image,
        contextual_text=(text or None),
        dimension=int(settings.vertex_vector_dimensions or 1408),
    )

    out: dict[str, list[float]] = {}
    if image is not None and embeddings.image_embedding:
        out["image"] = [float(v) for v in embeddings.image_embedding]
    if (text or "").strip() and embeddings.text_embedding:
        out["text"] = [float(v) for v in embeddings.text_embedding]
    return out
