import assert from 'node:assert/strict';
import test from 'node:test';
import { authenticationErrorMessage, SyncApiError } from './sync.ts';

test('authentication API rejections remain meaningful', () => {
  assert.equal(authenticationErrorMessage(new SyncApiError(409, 'Email already exists.'), 'connection failed'), 'Email already exists.');
});

test('only connection failures use the connection error message', () => {
  assert.equal(authenticationErrorMessage(new TypeError('fetch failed'), 'Unable to connect.'), 'Unable to connect.');
});
