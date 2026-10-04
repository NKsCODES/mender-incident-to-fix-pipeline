from checkout import cart


def test_cart_currency():
    assert cart.cart_currency([{"currency": "USD", "price_cents": 100, "qty": 1}]) == "USD"


def test_cart_total():
    assert cart.cart_total([{"currency": "USD", "price_cents": 100, "qty": 2}]) == 200
