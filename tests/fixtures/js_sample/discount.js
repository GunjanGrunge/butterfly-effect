'use strict';
// Tiny discount calculator used as a sample project. All data is invented.

const TIER_RATES = { guest: 0, member: 0.05, staff: 0.2 };
const COUPON_RATES = { SAVE10: 0.1, WELCOME25: 0.25 };
const EXPIRED_COUPONS = new Set(['SPRING2020']);
const COUPON_FORMAT = /^[A-Z]{3,12}[0-9]{0,4}$/;

class CouponError extends Error {}
class MalformedCouponError extends CouponError {}
class ExpiredCouponError extends CouponError {}

// total: cart total, a number >= 0 (a negative, NaN or infinite total throws RangeError)
// coupon: null/undefined, or a coupon code string (valid, expired or malformed)
// tier: 'guest', 'member' or 'staff'
// The two rates are added and capped at 100 percent, so the result is never negative.
// The result is rounded to 2 decimals.
function calculateDiscount(total, coupon = null, tier = 'guest') {
  if (typeof total !== 'number') {
    throw new TypeError('total must be a number');
  }
  if (!Number.isFinite(total)) {
    throw new RangeError('total must be a finite number');
  }
  if (total < 0) {
    throw new RangeError('total must not be negative');
  }
  if (!Object.prototype.hasOwnProperty.call(TIER_RATES, tier)) {
    throw new RangeError('unknown tier: ' + tier);
  }

  let rate = TIER_RATES[tier];
  if (coupon !== null && coupon !== undefined) {
    if (typeof coupon !== 'string' || !COUPON_FORMAT.test(coupon)) {
      throw new MalformedCouponError('malformed coupon');
    }
    if (EXPIRED_COUPONS.has(coupon)) {
      throw new ExpiredCouponError('coupon expired');
    }
    if (!Object.prototype.hasOwnProperty.call(COUPON_RATES, coupon)) {
      throw new MalformedCouponError('unknown coupon');
    }
    rate += COUPON_RATES[coupon];
  }

  rate = Math.min(rate, 1);
  return Math.round(total * (1 - rate) * 100) / 100;
}

module.exports = { calculateDiscount, CouponError, MalformedCouponError, ExpiredCouponError };
