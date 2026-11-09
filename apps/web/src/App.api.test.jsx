// @vitest-environment jsdom
import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, test, vi } from 'vitest';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import pg from 'pg';
import App from './App';

const databaseUrl = process.env.TEST_DATABASE_URL;
const databaseName = databaseUrl ? new URL(databaseUrl).pathname : '';
const enabled = Boolean(databaseUrl && databaseName.includes('_test'));
const port = 41000 + Math.floor(Math.random() * 8000);
const apiOrigin = `http://127.0.0.1:${port}`;
const nativeFetch = globalThis.fetch;
const nativeSetTimeout = globalThis.setTimeout.bind(globalThis);
let server;
let pool;
let patient;

async function api(path, init) {
  const response = await nativeFetch(`${apiOrigin}/api/${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  return { status: response.status, body: await response.json() };
}

async function eventually(assertion, attempts = 100) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt++) {
    try { return assertion(); } catch (error) { lastError = error; }
    await new Promise((resolveWait) => nativeSetTimeout(resolveWait, 10));
    await act(async () => {});
  }
  throw lastError;
}

describe.skipIf(!enabled)('React synchronization against PostgreSQL', () => {
  beforeAll(async () => {
    const apiFile = resolve(process.cwd(), '../../services/api/index.mjs');
    server = spawn(process.execPath, [apiFile], {
      env: { ...process.env, DATABASE_URL: databaseUrl, SYNC_PORT: String(port), TOKEN_SECRET: 'react-integration-test-secret' },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let diagnostics = '';
    server.stdout.on('data', (chunk) => { diagnostics += chunk; });
    server.stderr.on('data', (chunk) => { diagnostics += chunk; });
    for (let attempt = 0; attempt < 100; attempt++) {
      if (server.exitCode !== null) throw new Error(`API exited during startup: ${diagnostics}`);
      try { if ((await api('health')).status === 200) break; } catch {}
      await new Promise((resolveWait) => nativeSetTimeout(resolveWait, 25));
      if (attempt === 99) throw new Error(`API did not become ready: ${diagnostics}`);
    }
    const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    patient = { id: `react-sync-${suffix}`, email: `react-sync-${suffix}@example.test`, password: 'test-password' };
    const registered = await api('auth/bridge', { method: 'POST', body: JSON.stringify({ account: {
      id: patient.id, role: 'patient', email: patient.email, password: patient.password,
      patientProfile: { fullName: 'React Sync Patient', age: '30', weight: '70', height: '170', diabetesType: 'Type 1 Diabetes', selectedDoctorId: 'DR-001' },
    } }) });
    expect(registered.status).toBe(200);
    pool = new pg.Pool({ connectionString: databaseUrl });
  }, 15000);

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    globalThis.fetch = nativeFetch;
    localStorage.clear();
    sessionStorage.clear();
  });

  afterAll(async () => {
    await pool?.end();
    if (server && server.exitCode === null) {
      server.kill('SIGTERM');
      await new Promise((resolveExit) => server.once('exit', resolveExit));
    }
  });

  test('a form-created glucose reading uploads once across repeated polling cycles', async () => {
    vi.useFakeTimers();
    let glucosePosts = 0;
    let snapshotGets = 0;
    let uploadedId;
    globalThis.fetch = vi.fn(async (input, init) => {
      const raw = typeof input === 'string' ? input : input.url;
      const url = raw.startsWith('/api/') ? `${apiOrigin}${raw}` : raw;
      if (url.endsWith('/api/glucose') && init?.method === 'POST') {
        glucosePosts += 1;
        uploadedId = JSON.parse(init.body).id;
      }
      if (url.endsWith('/api/snapshot') && (!init?.method || init.method === 'GET')) snapshotGets += 1;
      return nativeFetch(url, init);
    });
    window.history.pushState({}, '', '/login/patient');
    render(<BrowserRouter><App /></BrowserRouter>);

    fireEvent.change(screen.getByLabelText('Email or username'), { target: { value: patient.email } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: patient.password } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await eventually(() => expect(screen.getByText('Welcome, React Sync Patient')).toBeTruthy());
    await eventually(() => expect(snapshotGets).toBeGreaterThanOrEqual(1));

    fireEvent.change(screen.getByLabelText('Glucose reading in mg/dL'), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));
    await eventually(() => expect(glucosePosts).toBe(1));
    await eventually(() => expect(JSON.parse(localStorage.getItem('ddt.glucose.v1')).find((item) => item.id === uploadedId)?.syncState).toBe('synced'));

    for (let poll = 0; poll < 4; poll++) {
      await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
      await new Promise((resolveWait) => nativeSetTimeout(resolveWait, 30));
      await act(async () => {});
    }

    expect(glucosePosts).toBe(1);
    expect(snapshotGets).toBeGreaterThanOrEqual(5);
    expect(Number((await pool.query('SELECT count(*) FROM glucose_readings WHERE id=$1', [uploadedId])).rows[0].count)).toBe(1);
  }, 15000);
});
