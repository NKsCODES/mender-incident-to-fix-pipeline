class CheckoutError(Exception):
    """Base class for expected, user-facing checkout failures."""


class UnsupportedCurrency(CheckoutError):
    pass


class OutOfStock(CheckoutError):
    pass
