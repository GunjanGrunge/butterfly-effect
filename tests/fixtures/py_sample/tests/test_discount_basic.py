import pytest

from discount import ExpiredCouponError, MalformedCouponError, calculate_discount


def test_guest_without_coupon_pays_full_price():
    assert calculate_discount(100.0) == 100.0


def test_member_with_valid_coupon():
    assert calculate_discount(200.0, "SAVE10", "member") == 170.0


def test_expired_coupon_is_rejected():
    with pytest.raises(ExpiredCouponError):
        calculate_discount(50.0, "SPRING2020")


def test_malformed_coupon_is_rejected():
    with pytest.raises(MalformedCouponError):
        calculate_discount(50.0, "no good!")
