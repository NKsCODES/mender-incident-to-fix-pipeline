import pytest

from checkout import coupon


def test_contract():
    assert coupon.parse_percent("10%") == 10
    assert coupon.parse_percent(" 15 % ") == 15
    with pytest.raises(ValueError):
        coupon.parse_percent("150%")
