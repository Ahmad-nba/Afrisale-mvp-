from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.models import Product, ProductVariant


def normalize_query(query: str) -> str:
    return (query or "").strip().lower().replace("-", " ")


def fuzzy_score(query: str, text_value: str) -> float:
    return float(fuzz.partial_ratio(query, text_value))


def _is_sqlite(db: Session) -> bool:
    bind = db.get_bind()
    return bool(bind and bind.dialect.name == "sqlite")


def _ensure_products_fts(db: Session) -> None:
    # products_fts rowid is aligned to products.id for direct lookup.
    db.execute(
        text(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS products_fts
            USING fts5(name, description, category)
            """
        )
    )
    db.execute(
        text(
            """
            INSERT INTO products_fts(rowid, name, description, category)
            SELECT p.id, p.name, p.description, ''
            FROM products p
            WHERE NOT EXISTS (
                SELECT 1 FROM products_fts f WHERE f.rowid = p.id
            )
            """
        )
    )


def _upsert_product_fts(db: Session, product: Product) -> None:
    db.execute(text("DELETE FROM products_fts WHERE rowid = :product_id"), {"product_id": product.id})
    db.execute(
        text(
            """
            INSERT INTO products_fts(rowid, name, description, category)
            VALUES (:product_id, :name, :description, :category)
            """
        ),
        {
            "product_id": product.id,
            "name": product.name,
            "description": product.description or "",
            "category": str(getattr(product, "category", "") or ""),
        },
    )


def search_products(db: Session, query: str) -> list[dict[str, Any]]:
    """
    Hybrid retrieval:
    1) FTS5 candidate retrieval
    2) RapidFuzz partial_ratio ranking by product name
    Returns rows for agent UI: title, price, variant_id, product_id (+ score).
    """
    q = normalize_query(query)
    if not q:
        return []

    if not _is_sqlite(db):
        # Safe fallback if DB engine is not SQLite.
        products = db.scalars(select(Product).order_by(Product.id)).all()
        results: list[dict[str, Any]] = []
        for p in products:
            score = fuzzy_score(q, normalize_query(p.name))
            if score < 35:
                continue
            variants = db.scalars(
                select(ProductVariant).where(ProductVariant.product_id == p.id).order_by(ProductVariant.id)
            ).all()
            for v in variants:
                results.append(
                    {
                        "title": f"{p.name} ({v.size}, {v.color})",
                        "description": p.description or "",
                        "price": v.price,
                        "variant_id": v.id,
                        "product_id": p.id,
                        "score": score,
                    }
                )
        results.sort(key=lambda row: float(row.get("score", 0.0)), reverse=True)
        return results[:5]

    _ensure_products_fts(db)

    match_query = " ".join(f"{token}*" for token in q.split() if token)
    if not match_query:
        return []

    candidate_rows = db.execute(
        text(
            """
            SELECT f.rowid AS product_id, p.name, p.description
            FROM products_fts f
            JOIN products p ON p.id = f.rowid
            WHERE products_fts MATCH :match_query
            LIMIT 20
            """
        ),
        {"match_query": match_query},
    ).mappings().all()
    if not candidate_rows:
        candidate_rows = db.execute(
            text(
                """
                SELECT p.id AS product_id, p.name, p.description
                FROM products p
                ORDER BY p.id
                LIMIT 20
                """
            )
        ).mappings().all()

    ranked_candidates: list[dict[str, Any]] = []
    for row in candidate_rows:
        name = str(row.get("name", "") or "")
        score = fuzzy_score(q, normalize_query(name))
        ranked_candidates.append({"product_id": int(row["product_id"]), "score": score, "name": name})

    ranked_candidates.sort(key=lambda item: item["score"], reverse=True)
    top_products = ranked_candidates[:5]

    results: list[dict[str, Any]] = []
    for candidate in top_products:
        product = db.get(Product, int(candidate["product_id"]))
        if not product:
            continue
        variants = db.scalars(
            select(ProductVariant).where(ProductVariant.product_id == product.id).order_by(ProductVariant.id)
        ).all()
        for v in variants:
            results.append(
                {
                    "title": f"{product.name} ({v.size}, {v.color})",
                    "description": product.description or "",
                    "price": v.price,
                    "variant_id": v.id,
                    "product_id": product.id,
                    "score": candidate["score"],
                }
            )
    return results


def get_products_formatted(db: Session) -> str:
    products = db.scalars(select(Product).order_by(Product.id)).all()
    if not products:
        return "No products in catalog yet."
    parts: list[str] = []
    for p in products:
        parts.append(f"- {p.name}: {p.description or 'No description'}")
        variants = db.scalars(
            select(ProductVariant).where(ProductVariant.product_id == p.id).order_by(ProductVariant.id)
        ).all()
        for v in variants:
            parts.append(
                f"  * Variant #{v.id} | size={v.size} | color={v.color} | price={v.price} | stock={v.stock_quantity}"
            )
    return "\n".join(parts)


def add_product(db: Session, name: str, description: str) -> str:
    p = Product(name=name.strip(), description=(description or "").strip())
    db.add(p)
    db.flush()
    if _is_sqlite(db):
        _ensure_products_fts(db)
        _upsert_product_fts(db, p)
    v = ProductVariant(
        product_id=p.id,
        size="Standard",
        color="Default",
        price=0,
        stock_quantity=0,
    )
    db.add(v)
    db.commit()
    return f"Product added (id={p.id}) with initial variant id={v.id}. Use update_price and update_stock to set catalog details."


def update_stock(db: Session, variant_id: int, quantity: int) -> str:
    v = db.get(ProductVariant, variant_id)
    if not v:
        return "Variant not found."
    v.stock_quantity = int(quantity)
    db.commit()
    return f"Stock for variant {variant_id} set to {v.stock_quantity}."


def update_price(db: Session, variant_id: int, price: int) -> str:
    v = db.get(ProductVariant, variant_id)
    if not v:
        return "Variant not found."
    v.price = int(price)
    db.commit()
    return f"Price for variant {variant_id} set to {v.price}."
