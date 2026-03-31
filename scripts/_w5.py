import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/guardrails/__init__.py", "")
w("app/guardrails/input_guardrails.py", r"""
import re

_MAX = 500
_KEYWORDS = frozenset(
    "order product price stock size color delivery hello hi help catalog shop buy pay status".split()
)


def validate_inbound_message(text: str | None) -> tuple[bool, str]:
    if text is None:
        return False, "Empty message."
    s = text.strip()
    if not s:
        return False, "Empty message."
    if len(s) > _MAX:
        return False, "Message too long. Please send a shorter message."
    if not _has_recognizable_intent(s):
        return False, "Sorry, I did not understand. Try asking about products, orders, or prices."
    return True, s


def _has_recognizable_intent(s: str) -> bool:
    if re.search(r"[A-Za-z0-9]", s):
        low = s.lower()
        tokens = re.findall(r"[a-z0-9]+", low)
        if any(t in _KEYWORDS for t in tokens):
            return True
        if len(s) >= 3:
            return True
    return False
""")
w("app/guardrails/output_guardrails.py", r"""
import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Product, ProductVariant

_FALLBACK = (
    "I can only share information that matches our catalog. Reply with what you want (size, color) "
    "or ask for our product list."
)


def load_catalog_hints(db: Session) -> tuple[set[str], set[int]]:
    names = {p.name.lower() for p in db.scalars(select(Product)).all()}
    prices = set(db.scalars(select(ProductVariant.price)).all())
    return names, prices


def validate_assistant_text(db: Session, text: str | None) -> str:
    if text is None:
        return _FALLBACK
    s = text.strip()
    if not s:
        return _FALLBACK
    names, prices = load_catalog_hints(db)
    low = s.lower()
    for name in names:
        if len(name) >= 3 and name in low:
            break
    else:
        if names and re.search(r"\b(ugx|kes|usd|rwf|tzs|shilling|price|cost)\b", low):
            pass
    nums = [int(m.group(0)) for m in re.finditer(r"\b\d+\b", s)]
    for n in nums:
        if n not in prices and n > 0:
            if _looks_like_price_claim(s, n):
                return _FALLBACK
    if names:
        for token in re.findall(r"[A-Za-z]{4,}", s):
            tl = token.lower()
            if tl in ("order", "status", "hello", "thanks", "please", "your", "this", "that", "with", "from", "have", "what", "when", "here", "shop"):
                continue
            if not any(tl in n or n in tl for n in names):
                if _token_might_be_product_name(token):
                    return _FALLBACK
    return s


def _looks_like_price_claim(s: str, n: int) -> bool:
    i = s.find(str(n))
    if i < 0:
        return False
    window = s[max(0, i - 12) : i + len(str(n)) + 12].lower()
    return any(k in window for k in ("ugx", "kes", "usd", "rwf", "tzs", "price", "cost", "shilling"))


def _token_might_be_product_name(token: str) -> bool:
    return token[0].isupper() and len(token) >= 4
""")
print("guardrails")
