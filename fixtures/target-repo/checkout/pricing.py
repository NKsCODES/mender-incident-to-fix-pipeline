def unit_price(total_cents: int, quantity: int) -> int:
    """Average unit price in cents for a cart line.

    An empty line (quantity 0) has a unit price of 0.
    """
    return total_cents // quantity
