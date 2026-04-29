from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import ConversationState


DEFAULT_STATE: dict[str, Any] = {
    "lastProductCandidates": [],
    "selectedProductId": None,
    "selectedVariantId": None,
    "lastMentionedPrice": None,
    "deliveryLocation": "",
    "lastInboundAttachments": [],
    "lastImageSearchMatches": [],
}


def _normalize_state(candidate: Any) -> dict[str, Any]:
    state = dict(DEFAULT_STATE)
    if isinstance(candidate, dict):
        state.update(candidate)
    return state


def get_state(db: Session, customer_id: int) -> dict[str, Any]:
    row = db.scalars(
        select(ConversationState).where(ConversationState.customer_id == customer_id)
    ).first()
    if not row:
        return dict(DEFAULT_STATE)
    try:
        payload = json.loads(row.state_json or "{}")
    except Exception:
        payload = {}
    return _normalize_state(payload)


def save_state(db: Session, customer_id: int, state: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_state(state)
    row = db.scalars(
        select(ConversationState).where(ConversationState.customer_id == customer_id)
    ).first()
    serialized = json.dumps(normalized, ensure_ascii=True)
    if not row:
        row = ConversationState(customer_id=customer_id, state_json=serialized)
        db.add(row)
    else:
        row.state_json = serialized
    db.commit()
    return normalized
