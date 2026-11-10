'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { calculateDiscount } = require('../discount');

for (const bad of [-0.01, -50, NaN, Infinity, -Infinity]) {
  test('invalid total ' + String(bad) + ' is rejected', () => {
    assert.throws(() => calculateDiscount(bad), RangeError);
  });
}

test('zero total is zero', () => {
  assert.strictEqual(calculateDiscount(0, 'WELCOME25', 'staff'), 0);
});
