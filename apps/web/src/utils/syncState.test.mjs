import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergeById, retryDecision, withoutLocalSyncMetadata } from './syncState.ts';
import { syncItem } from './sync.ts';

const leaked = { syncState: 'pending', syncAttempts: 3, syncNextAttemptAt: 1234, syncError: 'offline' };

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

test('leaked server metadata cannot requeue acknowledged records and durable local states survive', () => {
  const acknowledged = { id: 'reading', value: 120, syncState: 'synced' };
  assert.deepEqual(mergeById([acknowledged], [{ id: 'reading', value: 120, ...leaked }]), [{ id: 'reading', value: 120 }]);

  for (const syncState of ['pending', 'conflict', 'failed']) {
    const local = { id: syncState, value: 120, syncState, syncAttempts: 2 };
    const reloaded = JSON.parse(JSON.stringify([local]));
    assert.equal(mergeById(reloaded, [{ id: syncState, value: 121, ...leaked }])[0], reloaded[0]);
  }

  assert.deepEqual(
    mergeById([{ id: 'meal', version: 1, syncState: 'synced' }], [{ id: 'meal', version: 2, ...leaked }]),
    [{ id: 'meal', version: 2 }],
  );
});

test('upload serialization removes local metadata without mutating the durable queue entry', async () => {
  const originalFetch = globalThis.fetch;
  const originalSessionStorage = globalThis.sessionStorage;
  const sent = [];
  globalThis.sessionStorage = { getItem: () => 'test-token' };
  globalThis.fetch = async (url, init) => {
    sent.push({ url, body: JSON.parse(init.body) });
    return { ok: true, json: async () => ({ ok: true }) };
  };
  const queued = [
    ['glucose', { id: 'reading', patientSlug: 'patient', value: 120, recordedAt: '2026-01-01T13:10:00Z', ...leaked }],
    ['food', { id: 'meal', patientSlug: 'patient', announcedCarbsG: 30, plannedEatingAt: '2026-01-01T13:10:00Z', status: 'planned', recommendationId: 'rec-1', ...leaked }],
    ['bolus', { id: 'dose', patientSlug: 'patient', administeredUnits: 2, administeredAt: '2026-01-01T13:10:00Z', confirmationProvenance: { source: 'patient_log' }, ...leaked }],
    ['messages', { id: 'message', patientSlug: 'patient', doctorId: 'doctor', from: 'patient', text: 'Hello', sentAt: '2026-01-01T13:10:00Z', ...leaked }],
  ];
  try {
    for (const [kind, item] of queued) await syncItem(kind, item);
    assert.deepEqual(sent.map(({ url }) => url), ['/api/glucose', '/api/food', '/api/bolus', '/api/messages']);
    for (let index = 0; index < queued.length; index++) {
      assert.deepEqual(sent[index].body, withoutLocalSyncMetadata(queued[index][1]));
      assert.equal(queued[index][1].syncState, 'pending');
      assert.equal(queued[index][1].syncAttempts, 3);
    }
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.sessionStorage = originalSessionStorage;
  }
});

test('acknowledged upload remains non-pending through repeated legacy snapshots', async () => {
  const originalFetch = globalThis.fetch;
  const originalSessionStorage = globalThis.sessionStorage;
  let posts = 0;
  globalThis.sessionStorage = { getItem: () => 'test-token' };
  globalThis.fetch = async () => {
    posts += 1;
    return { ok: true, json: async () => ({ ok: true }) };
  };
  let local = [{ id: 'reading', patientSlug: 'patient', value: 120, recordedAt: '2026-01-01T13:10:00Z', syncState: 'pending' }];
  try {
    await syncItem('glucose', local[0]);
    local = [{ ...local[0], syncState: 'synced' }];
    for (let poll = 0; poll < 4; poll++) {
      local = mergeById(local, [{ id: 'reading', patientSlug: 'patient', value: 120, recordedAt: '2026-01-01T13:10:00.000Z', ...leaked }]);
      for (const item of local) if (item.syncState === 'pending') await syncItem('glucose', item);
    }
    assert.equal(posts, 1);
    assert.notEqual(local[0].syncState, 'pending');
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.sessionStorage = originalSessionStorage;
  }
});

test('conflicts stop immediately and transient retries use bounded backoff', () => {
  assert.deepEqual(retryDecision(409, 0, 1000), { state: 'conflict', attempts: 1 });
  assert.deepEqual(retryDecision(400, 0, 1000), { state: 'failed', attempts: 1 });
  assert.deepEqual(retryDecision(503, 0, 1000), { state: 'pending', attempts: 1, nextAttemptAt: 3000 });
  assert.deepEqual(retryDecision(undefined, 4, 1000), { state: 'failed', attempts: 5 });
});
