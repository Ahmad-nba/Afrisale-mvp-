from sqlalchemy.orm import Session

from app.services import catalog, catalog_image_ingest, orders, product_image_search


def derive_memory_update(tool_name: str, args: dict, tool_result) -> dict:
    update: dict = {}
    if tool_name in ("search_products", "find_products_by_text"):
        rows = tool_result if isinstance(tool_result, list) else []
        candidates = []
        for row in rows[:8]:
            if not isinstance(row, dict):
                continue
            candidates.append(
                {
                    "title": str(row.get("title") or row.get("name") or ""),
                    "price": int(row.get("price", 0) or 0),
                    "variant_id": row.get("variant_id"),
                    "product_id": row.get("product_id"),
                    "image_url": row.get("image_url", ""),
                }
            )
        update["lastProductCandidates"] = candidates
        if candidates:
            first = candidates[0]
            update["selectedVariantId"] = first.get("variant_id")
            update["selectedProductId"] = first.get("product_id")
            update["lastMentionedPrice"] = first.get("price")
        return update

    if tool_name in ("find_products_by_image", "get_product_image"):
        matches = tool_result if isinstance(tool_result, list) else []
        slim = []
        for match in matches[:8]:
            if not isinstance(match, dict):
                continue
            slim.append(
                {
                    "product_id": match.get("product_id"),
                    "name": match.get("name", ""),
                    "image_url": match.get("image_url", ""),
                    "similarity": float(match.get("similarity", 0.0)),
                }
            )
        update["lastImageSearchMatches"] = slim
        if slim:
            update["selectedProductId"] = slim[0].get("product_id")
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


def build_customer_tools(
    db: Session,
    customer_id: int,
    last_attachments: list[dict] | None = None,
    last_memory_state: dict | None = None,
) -> list:
    """
    Returns customer-role tool definitions.

    `last_attachments` is the list of inbound attachments for the current turn,
    so the image-search tool can pick up the latest image without the LLM
    needing to know the attachment id.

    `last_memory_state` exposes structured memory (e.g. `selectedProductId`)
    so tools like `get_product_image` can resolve "share an image of it" from
    prior turns without needing the LLM to remember the id.
    """
    last_attachments = list(last_attachments or [])
    last_memory_state = dict(last_memory_state or {})

    def handle_get_catalog(db: Session, **kwargs) -> str:
        return catalog.get_products_formatted(db)

    def handle_search_products(db: Session, **kwargs) -> list[dict]:
        query = str(kwargs.get("query", ""))
        results = catalog.search_products(db, query=query)
        if results:
            return results
        # Multimodal text fallback for descriptive queries ("Air Jordans").
        return product_image_search.search_by_text(db, query=query)

    def handle_find_products_by_text(db: Session, **kwargs) -> list[dict]:
        query = str(kwargs.get("query", ""))
        return product_image_search.search_by_text(db, query=query)

    def handle_find_products_by_image(db: Session, **kwargs) -> list[dict]:
        attachment_id = kwargs.get("attachment_id")
        if attachment_id is None and last_attachments:
            for descriptor in last_attachments:
                if str(descriptor.get("kind", "")).lower() == "image":
                    attachment_id = descriptor.get("id")
                    break
        if attachment_id is None:
            return []
        return product_image_search.search_by_image_attachment(
            db,
            attachment_id=int(attachment_id),
        )

    def handle_get_product_image(db: Session, **kwargs) -> list[dict]:
        product_id = kwargs.get("product_id")
        if product_id is None:
            product_id = last_memory_state.get("selectedProductId")
        if product_id is None:
            candidates = last_memory_state.get("lastProductCandidates") or []
            if isinstance(candidates, list) and candidates:
                first = candidates[0] if isinstance(candidates[0], dict) else {}
                product_id = first.get("product_id")
        if product_id is None:
            return []
        try:
            pid = int(product_id)
        except (TypeError, ValueError):
            return []
        return product_image_search.get_product_card(db, product_id=pid)

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
            description=(
                "Searches the catalog by keyword. Falls back to multimodal text "
                "embedding search when keyword search is empty."
            ),
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
            name="find_products_by_text",
            description=(
                "Multimodal text-to-image search. Use for descriptive product "
                "queries such as 'red leather belt' or 'air jordans'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=handle_find_products_by_text,
        ),
        _tool(
            name="find_products_by_image",
            description=(
                "Finds catalog products visually similar to a user-supplied image. "
                "Use this whenever the inbound message has an image attachment."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "attachment_id": {
                        "type": "integer",
                        "description": "Optional. If omitted the latest inbound image is used.",
                    },
                },
                "required": [],
            },
            handler=handle_find_products_by_image,
        ),
        _tool(
            name="get_product_image",
            description=(
                "Returns the catalog card for a specific product (image, name, "
                "price, variants). Use when the user asks to see, share, or send "
                "a photo of a product they have already discussed (e.g. 'share an "
                "image', 'send me a photo'). If no product_id is provided, the "
                "most recently selected product from memory is used."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "Optional. Defaults to memory.selectedProductId.",
                    },
                },
                "required": [],
            },
            handler=handle_get_product_image,
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


def build_owner_tools(
    db: Session,
    last_attachments: list[dict] | None = None,
) -> list:
    """
    Returns owner-role tool definitions. Includes `add_product_image` so the
    seller WhatsApp upload path (future) can register catalog images.
    """
    last_attachments = list(last_attachments or [])

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

    def handle_add_product_image(db: Session, **kwargs) -> str:
        product_id = int(kwargs["product_id"])
        attachment_id = kwargs.get("attachment_id")
        if attachment_id is None and last_attachments:
            for descriptor in last_attachments:
                if str(descriptor.get("kind", "")).lower() == "image":
                    attachment_id = descriptor.get("id")
                    break
        if attachment_id is None:
            return "No image attachment found on this turn. Please attach an image."
        is_primary = kwargs.get("is_primary")
        try:
            image = catalog_image_ingest.register_product_image_from_attachment(
                db,
                product_id=product_id,
                attachment_id=int(attachment_id),
                is_primary=is_primary,
            )
        except Exception as exc:  # noqa: BLE001
            return f"Could not register product image: {exc}"
        return (
            f"Product image registered (product_id={product_id}, image_id={image.id}, "
            f"primary={image.is_primary})."
        )

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
        _tool(
            name="add_product_image",
            description=(
                "Registers an inbound image as a catalog image for a product. "
                "Use after seller sends a product photo with text like "
                "'add this image to product 5'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer"},
                    "attachment_id": {
                        "type": "integer",
                        "description": "Optional; defaults to latest inbound image.",
                    },
                    "is_primary": {"type": "boolean"},
                },
                "required": ["product_id"],
            },
            handler=handle_add_product_image,
        ),
    ]
