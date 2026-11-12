import { test } from 'node:test';
import assert from 'node:assert/strict';
import { updateProfile } from '../store.mjs';

const captureDb = () => {
  const calls = [];
  return { calls, query: async (sql, values) => { calls.push({ sql, values }); return { rows: [] }; } };
};

test('blank optional patient profile numbers become null and explicit zero remains zero', async () => {
  const blankDb = captureDb();
  await updateProfile(blankDb, 'patient', 'patient', {
    fullName: 'Patient', age: ' ', weight: '', height: '\t', diagnosisYear: '  ',
  });
  assert.deepEqual([blankDb.calls[0].values[2], blankDb.calls[0].values[3], blankDb.calls[0].values[4], blankDb.calls[0].values[7]], [null, null, null, null]);
  assert.deepEqual(blankDb.calls[0].values.slice(12), [true, true, true, true]);

  const zeroDb = captureDb();
  await updateProfile(zeroDb, 'patient', 'patient', {
    fullName: 'Patient', age: 0, weight: '0', height: 0, diagnosisYear: '0',
  });
  assert.deepEqual([zeroDb.calls[0].values[2], zeroDb.calls[0].values[3], zeroDb.calls[0].values[4], zeroDb.calls[0].values[7]], [0, 0, 0, 0]);
});

test('omitted profile numbers are marked for preservation and invalid values are rejected', async () => {
  const omittedDb = captureDb();
  await updateProfile(omittedDb, 'patient', 'patient', { fullName: 'Patient' });
  assert.deepEqual(omittedDb.calls[0].values.slice(12), [false, false, false, false]);

  for (const [field, value] of [['age', -1], ['weight', false], ['height', 'bad'], ['diagnosisYear', 'Infinity']]) {
    const db = captureDb();
    await assert.rejects(updateProfile(db, 'patient', 'patient', { fullName: 'Patient', [field]: value }), /finite nonnegative number/);
    assert.equal(db.calls.length, 0);
  }
});

test('doctor experience uses the same profile-only blank and omission rules', async () => {
  const blankDb = captureDb();
  await updateProfile(blankDb, 'doctor', 'doctor', { fullName: 'Doctor', yearsExperience: ' ' });
  assert.equal(blankDb.calls[0].values[3], null);
  assert.equal(blankDb.calls[0].values[11], true);

  const omittedDb = captureDb();
  await updateProfile(omittedDb, 'doctor', 'doctor', { fullName: 'Doctor' });
  assert.equal(omittedDb.calls[0].values[11], false);
});
