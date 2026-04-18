from sqlalchemy.orm import Session

from app.services import catalog, orders


def derive_memory_update(tool_name: str, args: dict, tool_result) -> dict:
    update: dict = {}
    if tool_name == "search_products":
        rows = tool_result if isinstance(tool_result, list) else []
        candidates = []
        for row in rows[:8]:
            if not isinstance(row, dict):
                continue
            candidates.append(
                {
                    "title": str(row.get("title", "")),
                    "price": int(row.get("price", 0) or 0),
                    "variant_id": row.get("variant_id"),
                    "product_id": row.get("product_id"),
                }
            )
        update["lastProductCandidates"] = candidates
        if candidates:
            first = candidates[0]
            update["selectedVariantId"] = first.get("variant_id")
            update["selectedProductId"] = first.get("product_id")
            update["lastMentionedPrice"] = first.get("price")
        return update

    if tool_name == "create_order":
        if isinstance(args, dict):
            location = str(args.get("delivery_location", "")).strip()
            if location:
                update["deliveryLocation"] = location
            items = args.get("items")
            if isinstance(items, list) and items:
                first = items[0] if isinstance(items[0], dict) else {}
                variant_id = first.get("variant_id", first.get("product_id"))
                if variant_id is not None:
                    update["selectedVariantId"] = int(variant_id)
        return update

    return update


def _tool(
    name: str,
    description: str,
    parameters: dict,
    handler,
) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": handler,
    }


def build_customer_tools(db: Session, customer_id: int) -> list:
    """
    Returns Parlant tool definitions for customer role:
    - get_products_formatted(db) -> formatted catalog string
    - search_products(db, query) -> list of matching products (new)
    - create_order(db, customer_id, items) -> order confirmation
    - get_order_status(db, customer_id, order_id) -> status string
    """
    def handle_get_catalog(db: Session, **kwargs) -> str:
        return catalog.get_products_formatted(db)

    def handle_search_products(db: Session, **kwargs) -> list[dict]:
        query = str(kwargs.get("query", ""))
        return catalog.search_products(db, query=query)

    def handle_create_order(db: Session, **kwargs) -> dict:
        delivery_location = str(kwargs.get("delivery_location", "")).strip()
        if not delivery_location:
            raise ValueError("Delivery location is required before placing an order.")

        items = kwargs.get("items") or []
        if not isinstance(items, list) or not items:
            raise ValueError("At least one order item is required.")

        results: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each order item must be an object.")
            if "quantity" not in item:
                raise ValueError("Each order item must include quantity.")
            variant_or_product_id = item.get("variant_id", item.get("product_id"))
            if variant_or_product_id is None:
                raise ValueError("Each order item must include variant_id or product_id.")
            result = orders.create_order(
                db,
                customer_id=customer_id,
                product_variant_id=int(variant_or_product_id),
                quantity=int(item["quantity"]),
            )
            results.append(result)
        return {"results": results, "delivery_location": delivery_location}

    def handle_get_order_status(db: Session, **kwargs) -> str:
        order_id = int(kwargs["order_id"])
        return orders.check_order_status(db, customer_id=customer_id, order_id=order_id)

    return [
        _tool(
            name="get_catalog",
            description="Returns the full formatted product catalog.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=handle_get_catalog,
        ),
        _tool(
            name="search_products",
            description="Searches the catalog by keyword. Use this before get_catalog.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "search keyword or product name"},
                },
                "required": ["query"],
            },
            handler=handle_search_products,
        ),
        _tool(
            name="create_order",
            description="Places an order for the current customer.",
            parameters={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "integer"},
                                "variant_id": {"type": "integer"},
                                "quantity": {"type": "integer"},
                            },
                            "required": ["product_id", "quantity"],
                        },
                    },
                    "delivery_location": {
                        "type": "string",
                        "description": "Customer delivery address",
                    },
                },
                "required": ["items", "delivery_location"],
            },
            handler=handle_create_order,
        ),
        _tool(
            name="get_order_status",
            description="Returns the status of a specific order.",
            parameters={
                "type": "object",
                "properties": {"order_id": {"type": "integer"}},
                "required": ["order_id"],
            },
            handler=handle_get_order_status,
        ),
    ]


def build_owner_tools(db: Session) -> list:
    """
    Returns Parlant tool definitions for owner role:
    - add_product(db, ...) -> product
    - update_stock(db, product_id, qty) -> product
    - update_price(db, product_id, price) -> product
    - list_all_orders(db) -> formatted orders string
    """
    def handle_add_product(db: Session, **kwargs) -> str:
        return catalog.add_product(
            db,
            name=str(kwargs["name"]),
            description=str(kwargs.get("description", "")),
        )

    def handle_update_stock(db: Session, **kwargs) -> str:
        return catalog.update_stock(
            db,
            variant_id=int(kwargs["variant_id"]),
            quantity=int(kwargs["quantity"]),
        )

    def handle_update_price(db: Session, **kwargs) -> str:
        return catalog.update_price(
            db,
            variant_id=int(kwargs["variant_id"]),
            price=int(kwargs["price"]),
        )

    def handle_list_all_orders(db: Session, **kwargs) -> str:
        return orders.view_orders(db)

    return [
        _tool(
            name="add_product",
            description="Adds a product to the catalog.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name"],
            },
            handler=handle_add_product,
        ),
        _tool(
            name="update_stock",
            description="Updates stock quantity for a product variant.",
            parameters={
                "type": "object",
                "properties": {
                    "variant_id": {"type": "integer"},
                    "quantity": {"type": "integer"},
                },
                "required": ["variant_id", "quantity"],
            },
            handler=handle_update_stock,
        ),
        _tool(
            name="update_price",
            description="Updates price for a product variant.",
            parameters={
                "type": "object",
                "properties": {
                    "variant_id": {"type": "integer"},
                    "price": {"type": "integer"},
                },
                "required": ["variant_id", "price"],
            },
            handler=handle_update_price,
        ),
        _tool(
            name="list_all_orders",
            description="Lists all recent orders in formatted text.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=handle_list_all_orders,
        ),
    ]
