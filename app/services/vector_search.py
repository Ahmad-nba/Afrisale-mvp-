"""
Vertex AI Vector Search (Matching Engine) thin wrapper.

We treat each catalog product image as one datapoint. Datapoint IDs are
the `vector_datapoint_id` column on `product_images` so we can map matches
back to DB rows.

Design notes:
- Index and IndexEndpoint must be created once via gcloud or console.
- Upserts use streaming mode (`upsert_datapoints`) for low-latency MVP.
- Queries go through the public endpoint via `find_neighbors`.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Neighbor:
    datapoint_id: str
    distance: float
    similarity: float


def _ensure_credentials_env() -> None:
    cp = (settings.google_application_credentials or "").strip()
    if cp and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cp


def _init_vertex() -> None:
    from google.cloud import aiplatform

    _ensure_credentials_env()
    project = (settings.gcp_project_id or "").strip()
    location = (settings.gcp_location or "us-central1").strip()
    if not project:
        raise EnvironmentError("GCP_PROJECT_ID must be set for vector search.")
    aiplatform.init(project=project, location=location)


def _index():
    from google.cloud import aiplatform

    _init_vertex()
    index_id = (settings.vertex_vector_index_id or "").strip()
    if not index_id:
        raise EnvironmentError("VERTEX_VECTOR_INDEX_ID is not configured.")
    return aiplatform.MatchingEngineIndex(index_name=index_id)


def _index_endpoint():
    from google.cloud import aiplatform

    _init_vertex()
    endpoint_id = (settings.vertex_vector_index_endpoint_id or "").strip()
    if not endpoint_id:
        raise EnvironmentError("VERTEX_VECTOR_INDEX_ENDPOINT_ID is not configured.")
    return aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=endpoint_id)


def new_datapoint_id(prefix: str = "img") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def upsert_datapoint(
    datapoint_id: str,
    vector: list[float],
    restricts: Optional[list[dict]] = None,
) -> None:
    """
    Streams a single datapoint upsert into the index.

    `restricts` is the optional metadata filter list, e.g.:
        [{"namespace": "kind", "allow_list": ["product_image"]}]
    """
    from google.cloud.aiplatform.matching_engine.matching_engine_index_endpoint import (
        Namespace,
    )  # type: ignore

    _ = Namespace  # silence unused if import path differs across SDK versions
    index = _index()
    datapoint = {
        "datapoint_id": str(datapoint_id),
        "feature_vector": [float(v) for v in vector],
    }
    if restricts:
        datapoint["restricts"] = restricts
    index.upsert_datapoints(datapoints=[datapoint])
    logger.info("vvs_upsert ok id=%s dim=%d", datapoint_id, len(vector))


def remove_datapoint(datapoint_id: str) -> None:
    index = _index()
    try:
        index.remove_datapoints(datapoint_ids=[str(datapoint_id)])
    except Exception:
        logger.exception("vvs_remove_failed id=%s", datapoint_id)


def find_neighbors(
    vector: list[float],
    top_k: int = 5,
    deployed_index_id: Optional[str] = None,
) -> list[Neighbor]:
    """
    Queries the deployed index endpoint for nearest neighbors of `vector`.
    Returns a list of (datapoint_id, distance, similarity).

    Distance is the raw value returned by the index. Similarity is a
    monotonic transform we use for thresholding: higher is better.
    """
    endpoint = _index_endpoint()
    deployed_id = (
        deployed_index_id
        or settings.vertex_vector_deployed_index_id
        or ""
    ).strip()
    if not deployed_id:
        raise EnvironmentError("VERTEX_VECTOR_DEPLOYED_INDEX_ID is not configured.")

    matches = endpoint.find_neighbors(
        deployed_index_id=deployed_id,
        queries=[[float(v) for v in vector]],
        num_neighbors=int(max(1, top_k)),
    )

    results: list[Neighbor] = []
    if not matches:
        return results

    for neighbor in matches[0]:
        distance = float(getattr(neighbor, "distance", 0.0) or 0.0)
        # Vertex returns dot-product / cosine-like distances depending on
        # index config. Normalize to a similarity in [0, 1] for thresholding.
        # Cosine distance is in [0, 2]; cosine similarity in [-1, 1].
        # We keep the raw distance and a best-effort similarity.
        similarity = max(0.0, min(1.0, 1.0 - (distance / 2.0)))
        results.append(
            Neighbor(
                datapoint_id=str(neighbor.id),
                distance=distance,
                similarity=similarity,
            )
        )
    return results
