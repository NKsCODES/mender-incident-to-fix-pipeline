from checkout import cart


def test_contract():
    assert cart.cart_currency([]) == cart.DEFAULT_CURRENCY
    assert cart.cart_currency([{"currency": "USD"}]) == "USD"
