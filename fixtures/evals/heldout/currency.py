import pytest

from checkout import currency
from checkout.errors import UnsupportedCurrency


def test_contract():
    assert currency.convert(100, "usd", "inr") == 8300
    assert currency.convert(100, "Usd", "USD") == 100
    with pytest.raises(UnsupportedCurrency):
        currency.convert(100, "USD", "XYZ")
