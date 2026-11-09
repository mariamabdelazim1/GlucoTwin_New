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

async function eventually(label, assertion, attempts = 200) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt++) {
    try { return assertion(); } catch (error) { lastError = error; }
    await act(async () => {
      await new Promise((resolveWait) => nativeSetTimeout(resolveWait, 10));
    });
  }
  throw new Error(`Timed out waiting for ${label} after ${attempts * 10} ms: ${lastError?.message || lastError}`);
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
    let snapshotRequestsStarted = 0;
    let snapshotResponsesCompleted = 0;
    let uploadedId;
    globalThis.fetch = vi.fn(async (input, init) => {
      const raw = typeof input === 'string' ? input : input.url;
      const url = raw.startsWith('/api/') ? `${apiOrigin}${raw}` : raw;
      if (url.endsWith('/api/glucose') && init?.method === 'POST') {
        glucosePosts += 1;
        uploadedId = JSON.parse(init.body).id;
      }
      const isSnapshot = url.endsWith('/api/snapshot') && (!init?.method || init.method === 'GET');
      if (!isSnapshot) return nativeFetch(url, init);
      snapshotRequestsStarted += 1;
      const response = await nativeFetch(url, init);
      const body = await response.text();
      snapshotResponsesCompleted += 1;
      return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
    });

    const baselineId = `initial-snapshot-${patient.id}`;
    await pool.query(`INSERT INTO glucose_readings(id,patient_id,measured_at,glucose_mg_dl,source,legacy_payload)
      VALUES($1,$2,$3,111,'manual','{}')`, [baselineId, patient.id, new Date().toISOString()]);
    window.history.pushState({}, '', '/login/patient');
    render(<BrowserRouter><App /></BrowserRouter>);

    fireEvent.change(screen.getByLabelText('Email or username'), { target: { value: patient.email } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: patient.password } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await eventually('the patient dashboard to render after sign-in', () => expect(screen.getByText('Welcome, React Sync Patient')).toBeTruthy());
    await eventually('the initial snapshot request to start', () => expect(snapshotRequestsStarted).toBe(1));
    await eventually('the initial snapshot response body to complete', () => expect(snapshotResponsesCompleted).toBe(1));
    await eventually('React to render the initial snapshot reading', () => expect(screen.getByText('111 mg/dL')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('Glucose reading in mg/dL'), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));
    await eventually('the form-created glucose upload', () => expect(glucosePosts).toBe(1));
    await eventually('the uploaded record to be acknowledged in the durable queue', () => {
      expect(JSON.parse(localStorage.getItem('ddt.glucose.v1')).find((item) => item.id === uploadedId)?.syncState).toBe('synced');
    });

    let completedPollingCycles = 0;
    for (let poll = 0; poll < 4; poll++) {
      const markerValue = 201 + poll;
      const markerId = `poll-${poll}-${patient.id}`;
      await pool.query(`INSERT INTO glucose_readings(id,patient_id,measured_at,glucose_mg_dl,source,legacy_payload)
        VALUES($1,$2,$3,$4,'manual','{}')`, [markerId, patient.id, new Date(Date.now() + (poll + 1) * 1000).toISOString(), markerValue]);
      const expectedSnapshots = poll + 2;
      await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
      await eventually(`poll ${poll + 1} snapshot request to start`, () => expect(snapshotRequestsStarted).toBe(expectedSnapshots));
      await eventually(`poll ${poll + 1} snapshot response body to complete`, () => expect(snapshotResponsesCompleted).toBe(expectedSnapshots));
      await eventually(`React to apply poll ${poll + 1}`, () => expect(screen.getByText(`${markerValue} mg/dL`)).toBeTruthy());
      await eventually(`poll ${poll + 1} to leave the acknowledged upload out of the pending queue`, () => {
        const stored = JSON.parse(localStorage.getItem('ddt.glucose.v1')).find((item) => item.id === uploadedId);
        expect(stored).toBeTruthy();
        expect(stored.syncState).not.toBe('pending');
        expect(glucosePosts).toBe(1);
      });
      completedPollingCycles += 1;
    }

    expect(completedPollingCycles).toBe(4);
    expect(snapshotRequestsStarted).toBe(5);
    expect(snapshotResponsesCompleted).toBe(5);
    expect(glucosePosts).toBe(1);
    expect(Number((await pool.query('SELECT count(*) FROM glucose_readings WHERE id=$1', [uploadedId])).rows[0].count)).toBe(1);
  }, 30000);
});
