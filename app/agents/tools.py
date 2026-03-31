from sqlalchemy.orm import Session
from langchain_core.tools import StructuredTool

from app.services import catalog, orders


def build_customer_tools(db: Session, customer_id: int) -> list[StructuredTool]:
    def get_products() -> str:
        return catalog.get_products_formatted(db)

    def create_order(product_variant_id: int, quantity: int) -> str:
        return orders.create_order(db, customer_id, product_variant_id, quantity)

    def check_order_status(order_id: int) -> str:
        return orders.check_order_status(db, customer_id, order_id)

    return [
        StructuredTool.from_function(
            get_products,
            name="get_products",
            description="List all products and variants with ids, sizes, colors, prices, and stock.",
        ),
        StructuredTool.from_function(
            create_order,
            name="create_order",
            description="Create an order for the current customer. Args: product_variant_id, quantity.",
        ),
        StructuredTool.from_function(
            check_order_status,
            name="check_order_status",
            description="Show status and line items for an order id for this customer.",
        ),
    ]


def build_owner_tools(db: Session) -> list[StructuredTool]:
    def add_product(name: str, description: str) -> str:
        return catalog.add_product(db, name, description)

    def update_stock(variant_id: int, quantity: int) -> str:
        return catalog.update_stock(db, variant_id, quantity)

    def update_price(variant_id: int, price: int) -> str:
        return catalog.update_price(db, variant_id, price)

    def view_orders() -> str:
        return orders.view_orders(db)

    return [
        StructuredTool.from_function(
            add_product,
            name="add_product",
            description="Add a new product with name and description. Creates a default variant to set price/stock later.",
        ),
        StructuredTool.from_function(
            update_stock,
            name="update_stock",
            description="Set stock quantity for a product variant id.",
        ),
        StructuredTool.from_function(
            update_price,
            name="update_price",
            description="Set price (integer) for a product variant id.",
        ),
        StructuredTool.from_function(
            view_orders,
            name="view_orders",
            description="List recent orders with customer phone and totals.",
        ),
    ]
