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
let apiStderr = '';
let apiExit = null;
let registrationStatus = null;
let activeDiagnostics = () => '';

const safeError = (value) => value instanceof Error
  ? `${value.name}: ${value.message}`
  : typeof value === 'string' ? value : typeof value;

function sanitizedApiStderr() {
  return apiStderr.replace(/Bearer\s+\S+/gi, 'Bearer [redacted]').slice(-2000);
}

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
  throw new Error(`Timed out waiting for ${label} after ${attempts * 10} ms: ${lastError?.message || lastError}\n${activeDiagnostics()}`);
}

describe.skipIf(!enabled)('React synchronization against PostgreSQL', () => {
  beforeAll(async () => {
    const apiFile = resolve(process.cwd(), '../../services/api/index.mjs');
    server = spawn(process.execPath, [apiFile], {
      env: { ...process.env, DATABASE_URL: databaseUrl, SYNC_PORT: String(port), TOKEN_SECRET: 'react-integration-test-secret' },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let startupOutput = '';
    server.stdout.on('data', (chunk) => { startupOutput += chunk; });
    server.stderr.on('data', (chunk) => { apiStderr += chunk; });
    server.on('exit', (code, signal) => { apiExit = { code, signal }; });
    for (let attempt = 0; attempt < 100; attempt++) {
      if (server.exitCode !== null) throw new Error(`API exited during startup (${JSON.stringify(apiExit)}): ${sanitizedApiStderr() || startupOutput.slice(-2000)}`);
      try { if ((await api('health')).status === 200) break; } catch {}
      await new Promise((resolveWait) => nativeSetTimeout(resolveWait, 25));
      if (attempt === 99) throw new Error(`API did not become ready (${JSON.stringify(apiExit)}): ${sanitizedApiStderr() || startupOutput.slice(-2000)}`);
    }
    const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    patient = { id: `react-sync-${suffix}`, email: `react-sync-${suffix}@example.test`, password: 'test-password' };
    const registered = await api('auth/bridge', { method: 'POST', body: JSON.stringify({ account: {
      id: patient.id, role: 'patient', email: patient.email, password: patient.password,
      patientProfile: { fullName: 'React Sync Patient', age: '30', weight: '70', height: '170', diabetesType: 'Type 1 Diabetes', selectedDoctorId: 'DR-001' },
    } }) });
    registrationStatus = registered.status;
    expect(registered.status).toBe(200);
    pool = new pg.Pool({ connectionString: databaseUrl });
  }, 15000);

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    globalThis.fetch = nativeFetch;
    activeDiagnostics = () => '';
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
    const phases = {
      formSubmitted: false,
      loginRequestsStarted: 0,
      bridgeRequestsStarted: 0,
      loginResponseStatus: null,
      loginResponsesParsed: 0,
      bridgeResponseStatus: null,
      bridgeResponsesParsed: 0,
      snapshotRequestsStarted: 0,
      snapshotResponseStatus: null,
      snapshotResponsesParsed: 0,
      glucosePosts: 0,
      glucoseResponseStatuses: [],
      completedPollingCycles: 0,
    };
    let uploadedId;
    let pollingInterval;
    let intervalId = 1;
    const reactErrors = [];
    const originalConsoleError = console.error;
    vi.spyOn(console, 'error').mockImplementation((...args) => {
      reactErrors.push(args.map(safeError).join(' | '));
      originalConsoleError(...args);
    });
    vi.spyOn(window, 'setInterval').mockImplementation((callback, delay) => {
      const id = intervalId++;
      if (delay === 4000) pollingInterval = callback;
      return id;
    });
    vi.spyOn(window, 'clearInterval').mockImplementation(() => {});
    activeDiagnostics = () => JSON.stringify({
      apiExit,
      apiStderr: sanitizedApiStderr(),
      registrationStatus,
      ...phases,
      sessionStored: Boolean(sessionStorage.getItem('ddt.session.v1')),
      tokenStored: Boolean(sessionStorage.getItem('ddt.sync.token')),
      route: window.location.pathname,
      pollingIntervalRegistered: typeof pollingInterval === 'function',
      reactErrors,
    });

    const forwardJsonResponse = async (response, onParsed) => {
      const body = await response.text();
      const forwarded = new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
      forwarded.json = async () => {
        const parsed = JSON.parse(body);
        onParsed();
        return parsed;
      };
      return forwarded;
    };
    globalThis.fetch = vi.fn(async (input, init) => {
      const raw = typeof input === 'string' ? input : input.url;
      const url = raw.startsWith('/api/') ? `${apiOrigin}${raw}` : raw;
      if (url.endsWith('/api/glucose') && init?.method === 'POST') {
        phases.glucosePosts += 1;
        uploadedId = JSON.parse(init.body).id;
        try {
          const response = await nativeFetch(url, init);
          phases.glucoseResponseStatuses.push(response.status);
          return response;
        } catch (error) {
          reactErrors.push(`glucose request: ${safeError(error)}`);
          throw error;
        }
      }
      const isLogin = url.endsWith('/api/auth/login') && init?.method === 'POST';
      const isBridge = url.endsWith('/api/auth/bridge') && init?.method === 'POST';
      if (isLogin) phases.loginRequestsStarted += 1;
      if (isBridge) phases.bridgeRequestsStarted += 1;
      const isSnapshot = url.endsWith('/api/snapshot') && (!init?.method || init.method === 'GET');
      if (isSnapshot) phases.snapshotRequestsStarted += 1;
      try {
        const response = await nativeFetch(url, init);
        if (isLogin) {
          phases.loginResponseStatus = response.status;
          return forwardJsonResponse(response, () => { phases.loginResponsesParsed += 1; });
        }
        if (isBridge) {
          phases.bridgeResponseStatus = response.status;
          return forwardJsonResponse(response, () => { phases.bridgeResponsesParsed += 1; });
        }
        if (isSnapshot) {
          phases.snapshotResponseStatus = response.status;
          return forwardJsonResponse(response, () => { phases.snapshotResponsesParsed += 1; });
        }
        return response;
      } catch (error) {
        reactErrors.push(`request ${new URL(url).pathname}: ${safeError(error)}`);
        throw error;
      }
    });

    const baselineId = `initial-snapshot-${patient.id}`;
    await pool.query(`INSERT INTO glucose_readings(id,patient_id,measured_at,glucose_mg_dl,source,legacy_payload)
      VALUES($1,$2,$3,111,'manual','{}')`, [baselineId, patient.id, new Date().toISOString()]);
    window.history.pushState({}, '', '/login/patient');
    render(<BrowserRouter><App /></BrowserRouter>);

    fireEvent.change(screen.getByLabelText('Email or username'), { target: { value: patient.email } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: patient.password } });
    screen.getByRole('button', { name: 'Sign in' }).closest('form').addEventListener('submit', () => { phases.formSubmitted = true; }, { once: true });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await eventually('the sign-in form submit event', () => expect(phases.formSubmitted).toBe(true));
    await eventually('the login request to start after form submission', () => expect(phases.loginRequestsStarted).toBe(1));
    await eventually('the login response to return successfully', () => expect(phases.loginResponseStatus).toBe(200));
    await eventually('the login response JSON to be consumed', () => expect(phases.loginResponsesParsed).toBe(1));
    await eventually('the authenticated session to be stored', () => expect(JSON.parse(sessionStorage.getItem('ddt.session.v1')).id).toBe(patient.id));
    await eventually('routing to the patient dashboard', () => expect(window.location.pathname).toBe('/patient/dashboard'));
    await eventually('the patient dashboard to render after sign-in', () => expect(screen.getByText('Welcome, React Sync Patient')).toBeTruthy());
    await eventually('the initial snapshot request to start', () => expect(phases.snapshotRequestsStarted).toBe(1));
    await eventually('the initial snapshot response to return successfully', () => expect(phases.snapshotResponseStatus).toBe(200));
    await eventually('the initial snapshot response JSON to be consumed', () => expect(phases.snapshotResponsesParsed).toBe(1));
    await eventually('React to render the initial snapshot reading', () => expect(screen.getByText('111 mg/dL')).toBeTruthy());
    await eventually('the polling interval to be registered', () => expect(typeof pollingInterval).toBe('function'));
    expect(phases.glucosePosts).toBe(0);

    fireEvent.change(screen.getByLabelText('Glucose reading in mg/dL'), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));
    await eventually('the form-created glucose upload', () => expect(phases.glucosePosts).toBe(1));
    await eventually('the glucose upload response', () => expect(phases.glucoseResponseStatuses).toEqual([200]));
    await eventually('the uploaded record to be acknowledged in the durable queue', () => {
      expect(JSON.parse(localStorage.getItem('ddt.glucose.v1')).find((item) => item.id === uploadedId)?.syncState).toBe('synced');
    });

    for (let poll = 0; poll < 4; poll++) {
      const markerValue = 201 + poll;
      const markerId = `poll-${poll}-${patient.id}`;
      await pool.query(`INSERT INTO glucose_readings(id,patient_id,measured_at,glucose_mg_dl,source,legacy_payload)
        VALUES($1,$2,$3,$4,'manual','{}')`, [markerId, patient.id, new Date(Date.now() + (poll + 1) * 1000).toISOString(), markerValue]);
      const expectedSnapshots = poll + 2;
      await act(async () => { await pollingInterval(); });
      await eventually(`poll ${poll + 1} snapshot request to start`, () => expect(phases.snapshotRequestsStarted).toBe(expectedSnapshots));
      await eventually(`poll ${poll + 1} snapshot response JSON to be consumed`, () => expect(phases.snapshotResponsesParsed).toBe(expectedSnapshots));
      await eventually(`React to apply poll ${poll + 1}`, () => expect(screen.getByText(`${markerValue} mg/dL`)).toBeTruthy());
      await eventually(`poll ${poll + 1} to leave the acknowledged upload out of the pending queue`, () => {
        const stored = JSON.parse(localStorage.getItem('ddt.glucose.v1')).find((item) => item.id === uploadedId);
        expect(stored).toBeTruthy();
        expect(stored.syncState).not.toBe('pending');
        expect(phases.glucosePosts).toBe(1);
      });
      phases.completedPollingCycles += 1;
    }

    expect(phases.completedPollingCycles).toBe(4);
    expect(phases.snapshotRequestsStarted).toBe(5);
    expect(phases.snapshotResponsesParsed).toBe(5);
    expect(phases.glucosePosts).toBe(1);
    expect(Number((await pool.query('SELECT count(*) FROM glucose_readings WHERE id=$1', [uploadedId])).rows[0].count)).toBe(1);
    expect(reactErrors).toEqual([]);
  }, 30000);
});
