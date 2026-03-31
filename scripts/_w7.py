import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip("\n") + "\n", encoding="utf-8")

w("app/guardrails/output_guardrails.py", r"""
import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Product, ProductVariant

_FALLBACK = (
    "I can only share information that matches our catalog. Ask for our product list or clarify size and color."
)


def load_catalog_hints(db: Session) -> tuple[set[str], set[int]]:
    names = {p.name.lower() for p in db.scalars(select(Product)).all()}
    prices = set(db.scalars(select(ProductVariant.price)).all())
    return names, prices


def validate_assistant_text(db: Session, text: str | None) -> str:
    if text is None:
        return _FALLBACK
    s = str(text).strip()
    if not s:
        return _FALLBACK
    _, prices = load_catalog_hints(db)
    for m in re.finditer(r"(?i)\b(ugx|kes|usd|rwf|tzs)\s*[:\s]*([\d,]+)\b", s):
        val = int(m.group(2).replace(",", ""))
        if val not in prices:
            return _FALLBACK
    for m in re.finditer(r"\b\d+\b", s):
        val = int(m.group(0))
        if val in prices:
            continue
        window = s[max(0, m.start() - 16) : m.end() + 16].lower()
        if any(k in window for k in ("ugx", "kes", "usd", "rwf", "tzs", "price", "cost", "shilling")):
            return _FALLBACK
    names = {p.name.lower() for p in db.scalars(select(Product)).all()}
    if names:
        low = s.lower()
        for n in names:
            if len(n) >= 3 and n in low:
                break
        else:
            if re.search(
                r"\b(we have|we stock|try our|available:|catalog:|new arrival)\b",
                low,
            ):
                return _FALLBACK
    return s
""")
print("og")
