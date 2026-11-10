"""Tiny discount calculator used as a sample project. All data is invented."""
import math
import re

TIER_RATES = {"guest": 0.0, "member": 0.05, "staff": 0.20}
COUPON_RATES = {"SAVE10": 0.10, "WELCOME25": 0.25}
EXPIRED_COUPONS = {"SPRING2020"}
COUPON_FORMAT = re.compile(r"^[A-Z]{3,12}[0-9]{0,4}$")


class CouponError(ValueError):
    """Base class for coupon problems."""


class MalformedCouponError(CouponError):
    """The coupon text does not look like a coupon, or is not known."""


class ExpiredCouponError(CouponError):
    """The coupon is known but no longer valid."""


def calculate_discount(total, coupon=None, tier="guest"):
    """Return the total after the tier discount and the coupon discount.

    total:  cart total, a number >= 0 (a negative, NaN or infinite total raises ValueError)
    coupon: None, or a coupon code string (valid, expired or malformed)
    tier:   "guest", "member" or "staff"
    The two rates are added and capped at 100 percent, so the result is never negative.
    The result is rounded to 2 decimals.
    """
    if isinstance(total, bool) or not isinstance(total, (int, float)):
        raise TypeError("total must be a number")
    if math.isnan(total) or math.isinf(total):
        raise ValueError("total must be a finite number")
    if total < 0:
        raise ValueError("total must not be negative")
    if tier not in TIER_RATES:
        raise ValueError("unknown tier: %s" % tier)

    rate = TIER_RATES[tier]
    if coupon is not None:
        if not isinstance(coupon, str) or not COUPON_FORMAT.match(coupon):
            raise MalformedCouponError("malformed coupon")
        if coupon in EXPIRED_COUPONS:
            raise ExpiredCouponError("coupon expired")
        if coupon not in COUPON_RATES:
            raise MalformedCouponError("unknown coupon")
        rate += COUPON_RATES[coupon]

    rate = min(rate, 1.0)
    return round(total * (1.0 - rate), 2)
