import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import {
  authenticationErrorMessage,
  loginAccount,
  SyncApiError,
  SyncNetworkError,
  SyncResponseError,
  SyncStorageError,
} from './sync.ts';

const originalFetch = globalThis.fetch;
const originalSessionStorage = globalThis.sessionStorage;
const request = { email: 'patient@example.test', password: 'temporary-secret', role: 'patient' };
const account = { id: 'PT-1', role: 'patient', email: 'patient@example.test', patientProfile: { fullName: 'Patient One' } };
let stored;

beforeEach(() => {
  stored = new Map();
  globalThis.sessionStorage = {
    getItem: (key) => stored.get(key) ?? null,
    setItem: (key, value) => stored.set(key, value),
  };
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.sessionStorage = originalSessionStorage;
});

const response = (body, { ok = true, status = 200 } = {}) => ({ ok, status, json: async () => body });
const capture = async (operation) => {
  try { await operation(); }
  catch (error) { return error; }
  assert.fail('Expected operation to fail');
};

test('fetch failure is classified as a connection failure', async () => {
  globalThis.fetch = async () => { throw new TypeError('sensitive browser detail'); };
  const error = await capture(() => loginAccount(request));
  assert.ok(error instanceof SyncNetworkError);
  assert.equal(authenticationErrorMessage(error), 'Unable to connect to the care service. Check your connection and try again.');
});

test('API rejection preserves its meaningful safe message', async () => {
  globalThis.fetch = async () => response({ error: 'Incorrect email or password.' }, { ok: false, status: 401 });
  const error = await capture(() => loginAccount(request));
  assert.ok(error instanceof SyncApiError);
  assert.equal(authenticationErrorMessage(error), 'Incorrect email or password.');
});

test('successful response with an invalid account is a response error and saves no token', async () => {
  globalThis.fetch = async () => response({ token: 'must-not-be-saved', account: { role: 'patient' } });
  const error = await capture(() => loginAccount(request));
  assert.ok(error instanceof SyncResponseError);
  assert.equal(authenticationErrorMessage(error), 'The care service returned an invalid response. Please try again.');
  assert.equal(stored.has('ddt.sync.token'), false);
});

test('successful response with a missing or invalid token saves no token', async () => {
  for (const token of [undefined, '', 42]) {
    stored.clear();
    globalThis.fetch = async () => response({ token, account });
    const error = await capture(() => loginAccount(request));
    assert.ok(error instanceof SyncResponseError);
    assert.equal(authenticationErrorMessage(error), 'The care service returned an invalid response. Please try again.');
    assert.equal(stored.has('ddt.sync.token'), false);
  }
});

test('malformed successful JSON is a response error', async () => {
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('response body detail'); } });
  const error = await capture(() => loginAccount(request));
  assert.ok(error instanceof SyncResponseError);
  assert.equal(authenticationErrorMessage(error), 'The care service returned an invalid response. Please try again.');
});

test('browser storage failure has a separate safe message', async () => {
  globalThis.fetch = async () => response({ token: 'valid-token', account });
  globalThis.sessionStorage.setItem = () => { throw new Error('browser quota detail'); };
  const error = await capture(() => loginAccount(request));
  assert.ok(error instanceof SyncStorageError);
  assert.equal(authenticationErrorMessage(error), 'The browser could not save your session. Check browser storage settings and try again.');
});

test('unexpected exceptions use a neutral fallback without exposing details', () => {
  assert.equal(authenticationErrorMessage(new Error('internal sensitive detail')), 'Authentication could not be completed. Please try again.');
});
