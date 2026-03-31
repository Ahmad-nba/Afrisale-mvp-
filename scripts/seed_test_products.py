"""
Insert two catalog products for local testing (uses DATABASE_URL from .env).
Idempotent: skips a product if that name already exists. Run from repo root:
  python scripts/seed_test_products.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
import app.models.models  # noqa: F401, E402
from app.models.models import Product, ProductVariant  # noqa: E402

SPECS = [
    {
        "name": "Black T-Shirt",
        "description": "Cotton crew neck, regular fit",
        "size": "M",
        "color": "Black",
        "price": 25_000,
        "stock": 15,
    },
    {
        "name": "Denim Jeans",
        "description": "Classic straight leg",
        "size": "32",
        "color": "Blue",
        "price": 85_000,
        "stock": 8,
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        added = 0
        for spec in SPECS:
            found = db.scalars(select(Product).where(Product.name == spec["name"])).first()
            if found:
                continue
            p = Product(name=spec["name"], description=spec["description"])
            db.add(p)
            db.flush()
            db.add(
                ProductVariant(
                    product_id=p.id,
                    size=spec["size"],
                    color=spec["color"],
                    price=int(spec["price"]),
                    stock_quantity=int(spec["stock"]),
                )
            )
            added += 1
        db.commit()
        if added:
            print(f"OK: inserted {added} test product(s) (Black T-Shirt, Denim Jeans)")
        else:
            print("SKIP: test products already present")
    finally:
        db.close()


if __name__ == "__main__":
    main()
