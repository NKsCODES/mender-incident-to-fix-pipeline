from checkout import cart, coupon, currency, pricing, shipping, tax
from checkout.inventory import Inventory


def test_unit_price():
    assert pricing.unit_price(1000, 4) == 250


def test_convert():
    assert currency.convert(100, "USD", "INR") == 8300


def test_reserve():
    assert Inventory({"A": 3}).reserve("A", 2) == 1


def test_tax():
    assert tax.tax_cents(1000, "MH") == 180


def test_coupon():
    assert coupon.parse_percent("10") == 10


def test_eta():
    assert shipping.eta_days(800, "road") == 2
