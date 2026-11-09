import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergeById, retryDecision } from './syncState.ts';

test('downloaded records are merged without becoming pending uploads', () => {
  const result = mergeById([], [{ id: 'server', value: 120 }]);
  assert.deepEqual(result, [{ id: 'server', value: 120 }]);
  assert.equal(result[0].syncState, undefined);
});

test('pending local records survive snapshots and server meal versions replace acknowledged copies', () => {
  const pending = { id: 'local', value: 100, syncState: 'pending' };
  assert.equal(mergeById([pending], [{ id: 'local', value: 101 }])[0], pending);
  assert.deepEqual(mergeById([{ id: 'meal', version: 1, syncState: 'synced' }], [{ id: 'meal', version: 2 }]), [{ id: 'meal', version: 2 }]);
});

test('conflicts stop immediately and transient retries use bounded backoff', () => {
  assert.deepEqual(retryDecision(409, 0, 1000), { state: 'conflict', attempts: 1 });
  assert.deepEqual(retryDecision(400, 0, 1000), { state: 'failed', attempts: 1 });
  assert.deepEqual(retryDecision(503, 0, 1000), { state: 'pending', attempts: 1, nextAttemptAt: 3000 });
  assert.deepEqual(retryDecision(undefined, 4, 1000), { state: 'failed', attempts: 5 });
});
