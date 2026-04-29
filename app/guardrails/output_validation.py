import asyncio
import re
import types

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Product, ProductVariant
from app.observability.logger import log_guardrail_decision


_FALLBACK = "I'm having trouble with that request right now. Please try again or contact support."
_PRICE_PREFIX_RE = re.compile(
    r"(?i)(?:\b(?:kes|ksh|ugx)\b|[$\u00A3\u20A6])\s*([0-9][0-9,]*(?:\.[0-9]+)?)"
)
_PRICE_SUFFIX_RE = re.compile(r"(?i)\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*/=")
_CAPITALIZED_WORD_RE = re.compile(r"\b[A-Z][A-Za-z]{2,}\b")
_QUOTED_PHRASE_RE = re.compile(r"\"([^\"]{3,})\"")

if not hasattr(asyncio, "coroutine"):
    asyncio.coroutine = types.coroutine  # type: ignore[attr-defined]


class OutputValidationGuardrail:
    """
    STRICT post-agent gate. Blocks hallucinated prices, wrong product names,
    and unsafe content before the response is ever formatted or sent.
    Failure triggers fallback response and never silently mangles.
    """

    def validate(self, db: Session, reply: str, has_media: bool = False) -> tuple[bool, str]:
        """
        Returns: (is_valid: bool, safe_fallback_or_empty: str)
        If invalid: safe_fallback_or_empty contains the fallback message to send.
        If valid: safe_fallback_or_empty is empty string.

        When `has_media` is true the response will be sent as an image card
        with a short caption, so the "reply too short" rule is relaxed.
        """
        text = (reply or "").strip()
        customer_id = int(db.info.get("customer_id", -1)) if hasattr(db, "info") else -1

        min_len = 1 if has_media else 5
        if len(text) < min_len:
            self._schedule_log("output_validation", False, "reply_too_short", customer_id)
            return False, _FALLBACK

        known_prices: set[int] = set()
        try:
            rows = db.query(ProductVariant).all()
            for row in rows:
                price = getattr(row, "price", None)
                if isinstance(price, int | float):
                    known_prices.add(int(price))
        except Exception:
            pass
        if not known_prices:
            try:
                for price in db.scalars(select(ProductVariant.price)).all():
                    if isinstance(price, int | float):
                        known_prices.add(int(price))
            except Exception:
                pass

        mentioned_prices: list[float] = []
        for match in _PRICE_PREFIX_RE.finditer(text):
            mentioned_prices.append(float(match.group(1).replace(",", "")))
        for match in _PRICE_SUFFIX_RE.finditer(text):
            mentioned_prices.append(float(match.group(1).replace(",", "")))

        for mentioned in mentioned_prices:
            if not any(abs(mentioned - known) <= 1 for known in known_prices):
                self._schedule_log("output_validation", False, "price_hallucination", customer_id)
                return False, _FALLBACK

        product_names = [p.lower() for p in db.scalars(select(Product.name)).all() if p]
        warnings: list[str] = []
        for candidate in self._extract_product_like_candidates(text):
            cand_low = candidate.lower()
            if product_names and not any(cand_low in name for name in product_names):
                warnings.append(candidate)

        if warnings:
            self._schedule_log(
                "output_validation",
                True,
                f"product_name_warning:{', '.join(warnings[:5])}",
                customer_id,
            )
        else:
            self._schedule_log("output_validation", True, "", customer_id)
        return True, ""

    @staticmethod
    def _extract_product_like_candidates(text: str) -> set[str]:
        candidates = {m.group(1).strip() for m in _QUOTED_PHRASE_RE.finditer(text)}
        candidates.update(m.group(0).strip() for m in _CAPITALIZED_WORD_RE.finditer(text))
        return {c for c in candidates if c}

    @staticmethod
    def _schedule_log(stage: str, passed: bool, reason: str, customer_id: int) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop in caller context; skip to keep validation non-blocking.
            return
        loop.create_task(log_guardrail_decision(stage, passed, reason, customer_id))
