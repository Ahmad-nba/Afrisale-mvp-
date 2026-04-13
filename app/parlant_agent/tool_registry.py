from sqlalchemy.orm import Session


def build_customer_tools(db: Session, customer_id: int) -> list:
    """
    Returns Parlant tool definitions for customer role:
    - get_products_formatted(db) → formatted catalog string
    - search_products(db, query) → list of matching products   ← NEW, was missing
    - create_order(db, customer_id, items) → order confirmation
    - get_order_status(db, customer_id, order_id) → status string
    """
    pass


def build_owner_tools(db: Session) -> list:
    """
    Returns Parlant tool definitions for owner role:
    - add_product(db, ...) → product
    - update_stock(db, product_id, qty) → product
    - update_price(db, product_id, price) → product
    - list_all_orders(db) → formatted orders string
    """
    pass
