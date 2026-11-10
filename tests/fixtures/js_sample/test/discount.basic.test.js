'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { calculateDiscount, ExpiredCouponError, MalformedCouponError } = require('../discount');

test('guest without coupon pays full price', () => {
  assert.strictEqual(calculateDiscount(100), 100);
});

test('member with valid coupon', () => {
  assert.strictEqual(calculateDiscount(200, 'SAVE10', 'member'), 170);
});

test('expired coupon is rejected', () => {
  assert.throws(() => calculateDiscount(50, 'SPRING2020'), ExpiredCouponError);
});

test('malformed coupon is rejected', () => {
  assert.throws(() => calculateDiscount(50, 'no good!'), MalformedCouponError);
});
