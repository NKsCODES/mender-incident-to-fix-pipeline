from checkout import tax


def test_contract():
    assert tax.tax_cents(1000, None) == 0
    assert tax.tax_cents(1000, "mh") == 180
