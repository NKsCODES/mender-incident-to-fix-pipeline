from checkout import pricing


def test_contract():
    assert pricing.unit_price(0, 0) == 0
    assert pricing.unit_price(500, 0) == 0
    assert pricing.unit_price(1000, 4) == 250
