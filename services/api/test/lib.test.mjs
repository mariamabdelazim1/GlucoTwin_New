import { test } from 'node:test';
import assert from 'node:assert/strict';
import { finiteNonnegative, optionalNumber, strictUnit, timestamp } from '../lib.mjs';

test('strict numeric validation distinguishes missing, zero, and invalid input', () => {
  assert.equal(optionalNumber(undefined), null);
  assert.equal(optionalNumber(null), null);
  assert.equal(optionalNumber(0), 0);
  assert.equal(optionalNumber('0'), 0);
  assert.equal(finiteNonnegative('.5', 'Value'), 0.5);
  for (const value of [-1, false, true, '', ' ', '1x', 'NaN', 'Infinity', Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.throws(() => optionalNumber(value, 'Value'), /finite nonnegative number/);
  }
  assert.equal(strictUnit('45g', 'g', 'Carbs'), 45);
  assert.equal(strictUnit('2 U', 'U', 'Insulin'), 2);
  assert.throws(() => strictUnit(' ', 'g', 'Carbs'));
  assert.throws(() => strictUnit('', 'U', 'Insulin'));
  assert.throws(() => strictUnit('2ish U', 'U', 'Insulin'));
});

test('medical timestamps require an explicit timezone', () => {
  assert.equal(timestamp('2026-11-09T12:00:00+02:00'), '2026-11-09T10:00:00.000Z');
  assert.equal(timestamp('2026-11-09T10:00:00Z'), '2026-11-09T10:00:00.000Z');
  assert.throws(() => timestamp('2026-11-09T10:00:00'), /explicit UTC offset/);
  assert.throws(() => timestamp('not-a-date'), /full ISO timestamp/);
});
