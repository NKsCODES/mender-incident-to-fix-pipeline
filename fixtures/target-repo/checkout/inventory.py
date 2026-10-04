from checkout.errors import OutOfStock


class Inventory:
    def __init__(self, stock: dict[str, int]):
        self.stock = dict(stock)

    def reserve(self, sku: str, qty: int) -> int:
        """Reserve qty units and return what is left.

        Raises OutOfStock when the sku is unknown or stock is insufficient.
        """
        remaining = self.stock.get(sku) - qty
        if remaining < 0:
            raise OutOfStock(sku)
        self.stock[sku] = remaining
        return remaining
