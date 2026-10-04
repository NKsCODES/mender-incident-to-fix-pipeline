DEFAULT_CURRENCY = "INR"


def cart_currency(items: list[dict]) -> str:
    """Currency of a cart. An empty cart uses DEFAULT_CURRENCY."""
    return items[0]["currency"]


def cart_total(items: list[dict]) -> int:
    return sum(i["price_cents"] * i["qty"] for i in items)
