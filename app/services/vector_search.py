"""
Local NumPy cosine-similarity scan over `product_images.embedding_json`.

This is the MVP replacement for Vertex AI Vector Search. At catalog scale
(<1k images) a single NumPy matmul over a 1408-dim matrix is sub-millisecond,
so we do not need an ANN index.

Public surface preserved (callers are unchanged):
    - `Neighbor` dataclass
    - `new_datapoint_id(prefix)` -> str
    - `upsert_datapoint(datapoint_id, vector, restricts=None)` -> no-op stub
      (vectors are now persisted directly on `ProductImage.embedding_json`
      by `catalog_image_ingest.register_product_image`).
    - `find_neighbors(vector, top_k, db=None)` -> list[Neighbor]

Storage layout: each `ProductImage` row carries a JSON-encoded list of floats
in `embedding_json`. Rows with empty embeddings are skipped at query time.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class Neighbor:
    datapoint_id: str
    distance: float
    similarity: float


def new_datapoint_id(prefix: str = "img") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def upsert_datapoint(
    datapoint_id: str,
    vector: list[float],
    restricts: Optional[list[dict]] = None,
) -> None:
    """
    Deprecated under the local-cosine path. Vectors are persisted directly
    on the `ProductImage` row by `catalog_image_ingest.register_product_image`.

    Kept as a no-op stub so any legacy caller does not break.
    """
    _ = datapoint_id, vector, restricts
    logger.debug(
        "vector_search.upsert_datapoint is a no-op under the local path; "
        "vectors are stored on ProductImage.embedding_json"
    )


def remove_datapoint(datapoint_id: str) -> None:
    """No-op under the local path; deleting the `ProductImage` row removes
    the vector from search automatically."""
    _ = datapoint_id


def _load_catalog_vectors(db: Session) -> tuple[list[str], "object"]:
    """
    Returns (datapoint_ids, matrix) where `matrix` is an (N, dim) numpy array
    of L2-normalized vectors. N may be 0 if the catalog has no embeddings yet.
    """
    import numpy as np

    from app.models.models import ProductImage

    rows = db.execute(
        select(ProductImage.vector_datapoint_id, ProductImage.embedding_json)
    ).all()

    ids: list[str] = []
    vectors: list[list[float]] = []
    expected_dim: int | None = None

    for datapoint_id, embedding_json in rows:
        if not embedding_json:
            continue
        try:
            decoded = json.loads(embedding_json)
        except Exception:
            logger.warning(
                "vector_search skip row datapoint_id=%s reason=bad_json", datapoint_id
            )
            continue
        if not isinstance(decoded, list) or not decoded:
            continue
        if expected_dim is None:
            expected_dim = len(decoded)
        elif len(decoded) != expected_dim:
            logger.warning(
                "vector_search skip row datapoint_id=%s dim=%d expected=%d",
                datapoint_id,
                len(decoded),
                expected_dim,
            )
            continue
        ids.append(str(datapoint_id))
        vectors.append([float(v) for v in decoded])

    if not vectors:
        return [], np.zeros((0, 0), dtype=np.float32)

    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms
    return ids, matrix


def find_neighbors(
    vector: list[float],
    top_k: int = 5,
    db: Optional[Session] = None,
    deployed_index_id: Optional[str] = None,  # accepted for backward-compat
) -> list[Neighbor]:
    """
    Local cosine nearest-neighbor search over all `ProductImage` rows that
    have a populated `embedding_json`.

    `similarity` is cosine in [-1, 1] (typically 0..1 for multimodal embeddings).
    `distance` is `1 - similarity` for callers that prefer a distance metric.
    """
    import numpy as np

    _ = deployed_index_id  # kept for signature compatibility

    if not vector:
        return []

    own_session = db is None
    if own_session:
        from app.core.database import SessionLocal

        db = SessionLocal()

    try:
        ids, matrix = _load_catalog_vectors(db)
    finally:
        if own_session:
            try:
                db.close()
            except Exception:
                pass

    if matrix.shape[0] == 0:
        return []

    query = np.asarray([float(v) for v in vector], dtype=np.float32)
    if query.shape[0] != matrix.shape[1]:
        logger.warning(
            "vector_search query_dim=%d catalog_dim=%d mismatch; returning []",
            int(query.shape[0]),
            int(matrix.shape[1]),
        )
        return []
    qn = float(np.linalg.norm(query))
    if qn == 0.0:
        return []
    query = query / qn

    sims = matrix @ query  # (N,)
    k = int(max(1, top_k))
    if k >= sims.shape[0]:
        order = np.argsort(-sims)
    else:
        # argpartition for top-k, then sort the slice
        part = np.argpartition(-sims, k - 1)[:k]
        order = part[np.argsort(-sims[part])]

    results: list[Neighbor] = []
    for idx in order[:k]:
        sim = float(sims[int(idx)])
        results.append(
            Neighbor(
                datapoint_id=ids[int(idx)],
                distance=float(1.0 - sim),
                similarity=sim,
            )
        )
    return results
