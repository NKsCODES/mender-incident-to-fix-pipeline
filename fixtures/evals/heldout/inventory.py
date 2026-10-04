import pytest

from checkout.errors import OutOfStock
from checkout.inventory import Inventory


def test_contract():
    inv = Inventory({"A": 1})
    with pytest.raises(OutOfStock):
        inv.reserve("ZZ-9", 1)
    assert inv.reserve("A", 1) == 0
