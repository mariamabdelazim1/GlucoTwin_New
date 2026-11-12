import assert from 'node:assert/strict';
import test from 'node:test';
import { chronologicalMessages, latestConversations } from './messages.ts';

const message = (id, patientSlug, sentAt, time = 'Now') => ({
  id, patientSlug, patient: patientSlug, avatar: '', from: 'patient', text: id, time, sentAt,
});

test('messages use full timestamps and IDs for stable chronological ordering', () => {
  const rows = [
    message('z', 'one', '2026-11-09T23:24:00.000Z', '11:24 PM'),
    message('b', 'one', '2026-11-09T23:23:00.000Z', 'Now'),
    message('a', 'one', '2026-11-09T23:23:00.000Z', '11:23 PM'),
  ];
  assert.deepEqual(chronologicalMessages(rows).map(({ id }) => id), ['a', 'b', 'z']);
  assert.deepEqual(rows.map(({ id }) => id), ['z', 'b', 'a']);
});

test('conversation summaries use the latest message and remain most-recent first', () => {
  const rows = [
    message('a', 'one', '2026-11-09T20:00:00.000Z'),
    message('b', 'two', '2026-11-09T22:00:00.000Z'),
    message('c', 'one', '2026-11-09T23:00:00.000Z'),
  ];
  assert.deepEqual(latestConversations(rows).map(({ id }) => id), ['c', 'b']);
});
