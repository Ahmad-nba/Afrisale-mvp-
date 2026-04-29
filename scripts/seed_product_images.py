"""
Bulk-ingest catalog product images.

Usage:
    python scripts/seed_product_images.py --dir path/to/images
    python scripts/seed_product_images.py --map images.json

Folder mode:
    Images named like `<product_id>__anything.jpg` are matched by id.
    Images named like `<product_name>.jpg` are matched by exact product name
    (case-insensitive). Multiple images per product are allowed; the first
    one ingested for a product becomes its primary image.

Map mode (JSON):
    [
        {"product_id": 1, "path": "absolute/or/relative/path.jpg", "is_primary": true},
        {"product_name": "Demo Hoodie", "path": "another.png"}
    ]

Idempotent: an image whose `gcs_uri` already exists in `product_images` is
skipped (handy if you re-run after partial failures).
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import select  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
import app.models.models  # noqa: E402, F401
from app.models.models import Product, ProductImage  # noqa: E402
from app.services import catalog_image_ingest  # noqa: E402

logger = logging.getLogger("seed_product_images")


def _read_image(path: Path) -> tuple[bytes, str]:
    data = path.read_bytes()
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "image/jpeg"
    return data, mime


def _resolve_product(db, *, product_id: int | None, product_name: str | None) -> Product | None:
    if product_id is not None:
        prod = db.get(Product, int(product_id))
        if prod:
            return prod
    if product_name:
        prod = db.scalars(
            select(Product).where(Product.name.ilike(product_name.strip()))
        ).first()
        if prod:
            return prod
    return None


def _already_ingested(db, gcs_uri_prefix_marker: str) -> bool:
    # We cannot know the gcs_uri ahead of upload, so we treat re-runs as
    # additive. The owner can manually delete duplicate ProductImage rows
    # (and corresponding Vertex datapoints) if needed.
    return False


def _process_one(db, *, product: Product, image_path: Path, is_primary: bool | None) -> ProductImage:
    data, mime = _read_image(image_path)
    return catalog_image_ingest.register_product_image(
        db,
        product_id=product.id,
        image_bytes=data,
        mime_type=mime,
        is_primary=is_primary,
    )


def run_folder(folder: Path) -> None:
    db = SessionLocal()
    try:
        files = sorted([p for p in folder.iterdir() if p.is_file()])
        if not files:
            print(f"No files in {folder}")
            return
        ok = 0
        for path in files:
            stem = path.stem
            product = None
            if "__" in stem:
                head = stem.split("__", 1)[0].strip()
                if head.isdigit():
                    product = _resolve_product(db, product_id=int(head), product_name=None)
            if not product:
                product = _resolve_product(db, product_id=None, product_name=stem)
            if not product:
                print(f"SKIP {path.name}: no matching product (by id or name)")
                continue
            try:
                image = _process_one(db, product=product, image_path=path, is_primary=None)
                print(f"OK   {path.name} -> product_id={product.id} image_id={image.id}")
                ok += 1
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {path.name}: {exc}")
        print(f"Done. Registered {ok} images.")
    finally:
        db.close()


def run_map(map_file: Path) -> None:
    with map_file.open("r", encoding="utf-8") as fp:
        entries = json.load(fp)
    if not isinstance(entries, list):
        raise ValueError("Map file must contain a JSON list of entries.")

    db = SessionLocal()
    try:
        ok = 0
        for entry in entries:
            if not isinstance(entry, dict):
                print(f"SKIP malformed entry: {entry!r}")
                continue
            path = Path(str(entry.get("path", ""))).expanduser()
            if not path.is_absolute():
                path = (map_file.parent / path).resolve()
            if not path.exists():
                print(f"SKIP missing file {path}")
                continue
            product = _resolve_product(
                db,
                product_id=entry.get("product_id"),
                product_name=entry.get("product_name"),
            )
            if not product:
                print(f"SKIP {path.name}: no matching product for entry {entry!r}")
                continue
            is_primary = entry.get("is_primary")
            try:
                image = _process_one(db, product=product, image_path=path, is_primary=is_primary)
                print(f"OK   {path.name} -> product_id={product.id} image_id={image.id}")
                ok += 1
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {path.name}: {exc}")
        print(f"Done. Registered {ok} images.")
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed product images into GCS + Vertex Vector Search + DB.")
    parser.add_argument("--dir", type=str, help="Folder of images named by product id or name.")
    parser.add_argument("--map", type=str, help="JSON map file linking images to products.")
    args = parser.parse_args()

    if not args.dir and not args.map:
        parser.error("Provide either --dir or --map.")

    Base.metadata.create_all(bind=engine)

    if args.dir:
        folder = Path(args.dir).expanduser().resolve()
        if not folder.is_dir():
            parser.error(f"--dir not a directory: {folder}")
        run_folder(folder)

    if args.map:
        map_file = Path(args.map).expanduser().resolve()
        if not map_file.is_file():
            parser.error(f"--map not a file: {map_file}")
        run_map(map_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
