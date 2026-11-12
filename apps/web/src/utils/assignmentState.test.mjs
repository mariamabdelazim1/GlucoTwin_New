import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AssignmentDecisionError, confirmAssignmentDecision } from './assignmentState.ts';

const pending = { id: 'a1', patientId: 'patient', doctorId: 'doctor', status: 'pending' };

test('a confirmed assignment decision is returned without reconciliation', async () => {
  let snapshots = 0;
  const result = await confirmAssignmentDecision('patient', 'doctor', 'accepted', async () => ({ assignment: { ...pending, status: 'accepted' } }), async () => { snapshots += 1; return []; });
  assert.equal(result.assignment.status, 'accepted');
  assert.equal(result.reconciled, false);
  assert.equal(snapshots, 0);
});

test('a lost response is reconciled from authoritative assignments', async () => {
  const result = await confirmAssignmentDecision('patient', 'doctor', 'declined', async () => { throw new Error('Network lost'); }, async () => [{ ...pending, status: 'declined' }]);
  assert.equal(result.assignment.status, 'declined');
  assert.equal(result.reconciled, true);
});

test('a failed decision retains the authoritative pending state and reports an error', async () => {
  await assert.rejects(
    confirmAssignmentDecision('patient', 'doctor', 'accepted', async () => { throw new Error('Server unavailable'); }, async () => [pending]),
    (error) => error instanceof AssignmentDecisionError && error.current.status === 'pending' && error.assignments.length === 1 && /remains pending/.test(error.message),
  );
});
