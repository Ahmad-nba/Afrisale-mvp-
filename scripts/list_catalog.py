"""
List the catalog (products, variants, image coverage) for the current DB.

Usage:
    python scripts/list_catalog.py                # all products
    python scripts/list_catalog.py --missing      # only products with no images
    python scripts/list_catalog.py --json         # machine-readable

Reads DATABASE_URL from .env (defaults to sqlite:///./afrisale.db).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
import app.models.models  # noqa: E402, F401
from app.models.models import Product, ProductImage, ProductVariant  # noqa: E402


def _collect() -> list[dict]:
    db = SessionLocal()
    try:
        products = db.scalars(select(Product).order_by(Product.id)).all()
        rows: list[dict] = []
        for prod in products:
            variants = db.scalars(
                select(ProductVariant).where(ProductVariant.product_id == prod.id).order_by(ProductVariant.id)
            ).all()
            images = db.scalars(
                select(ProductImage).where(ProductImage.product_id == prod.id).order_by(ProductImage.id)
            ).all()
            primary = next((img for img in images if img.is_primary), images[0] if images else None)
            rows.append(
                {
                    "id": prod.id,
                    "name": prod.name,
                    "description": (prod.description or "")[:120],
                    "variants": [
                        {
                            "id": v.id,
                            "size": v.size,
                            "color": v.color,
                            "price": v.price,
                            "stock": v.stock_quantity,
                        }
                        for v in variants
                    ],
                    "images_count": len(images),
                    "primary_image_url": primary.public_url if primary else "",
                    "primary_image_gcs": primary.gcs_uri if primary else "",
                }
            )
        return rows
    finally:
        db.close()


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("(no products)")
        return
    print(f"{'ID':<4} {'IMGS':<5} {'NAME':<40} {'VARIANTS'}")
    print("-" * 100)
    for r in rows:
        variants = ", ".join(
            f"{v['size'] or '-'}/{v['color'] or '-'} @{v['price']} (stock {v['stock']})"
            for v in r["variants"]
        ) or "(no variants)"
        print(f"{r['id']:<4} {r['images_count']:<5} {r['name'][:40]:<40} {variants}")
        if r["primary_image_url"]:
            print(f"        primary: {r['primary_image_url']}")
    print()
    total = len(rows)
    with_imgs = sum(1 for r in rows if r["images_count"] > 0)
    print(f"Total products: {total}  |  With images: {with_imgs}  |  Missing images: {total - with_imgs}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--missing", action="store_true", help="Show only products with no images.")
    parser.add_argument("--json", action="store_true", help="Print as JSON.")
    args = parser.parse_args()

    rows = _collect()
    if args.missing:
        rows = [r for r in rows if r["images_count"] == 0]

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
