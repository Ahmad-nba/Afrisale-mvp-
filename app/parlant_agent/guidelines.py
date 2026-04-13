def customer_guidelines() -> list:
    """
    Returns Parlant guideline objects for customer-facing conversations.
    Intent: help customer browse catalog, search products, place orders.
    Must ask for delivery location before confirming any order.
    Must not quote prices not present in the DB.
    """
    pass


def owner_guidelines() -> list:
    """
    Returns Parlant guideline objects for owner-facing conversations.
    Intent: add/update products, view orders, adjust stock and price.
    Must not expose other customers' data.
    """
    pass
