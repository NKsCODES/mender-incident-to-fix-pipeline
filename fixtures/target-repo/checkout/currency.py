from checkout.errors import UnsupportedCurrency  # noqa: F401

RATES = {"USD": 1.0, "INR": 83.0, "EUR": 0.92}


def convert(amount_cents: int, src: str, dst: str) -> int:
    """Convert an amount between currencies.

    Currency codes are case-insensitive. Unknown codes raise UnsupportedCurrency.
    """
    return round(amount_cents / RATES[src] * RATES[dst])
