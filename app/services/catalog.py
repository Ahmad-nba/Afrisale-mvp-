from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Product, ProductVariant


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
