import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createPool } from '../db.mjs';
import { passwordHash } from '../lib.mjs';

const databaseUrl = process.env.TEST_DATABASE_URL;
if (!databaseUrl || !new URL(databaseUrl).pathname.includes('_test')) {
  throw new Error('TEST_DATABASE_URL must point to a database whose name contains _test');
}
const apiFile = fileURLToPath(new URL('../index.mjs', import.meta.url));
const importFile = fileURLToPath(new URL('../scripts/import-json.mjs', import.meta.url));
const runId = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
const port = 40000 + Math.floor(Math.random() * 10000);
const base = `http://127.0.0.1:${port}/api/`;

const request = async (path, { token, method = 'GET', data } = {}) => {
  const response = await fetch(base + path, {
    method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  return { status: response.status, body: await response.json() };
};

async function startServer() {
  const child = spawn(process.execPath, [apiFile], {
    env: { ...process.env, DATABASE_URL: databaseUrl, SYNC_PORT: String(port), TOKEN_SECRET: 'integration-test-secret' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let diagnostics = '';
  child.stdout.on('data', (chunk) => { diagnostics += chunk; });
  child.stderr.on('data', (chunk) => { diagnostics += chunk; });
  for (let attempt = 0; attempt < 80; attempt++) {
    if (child.exitCode !== null) throw new Error(`API exited during startup: ${diagnostics}`);
    try { if ((await request('health')).status === 200) return child; } catch {}
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  child.kill();
  throw new Error(`API did not become ready: ${diagnostics}`);
}

async function stopServer(child) {
  child.kill('SIGTERM');
  await new Promise((resolve) => child.once('exit', resolve));
}

const login = async (email, password, role = 'patient') => {
  const result = await request('auth/login', { method: 'POST', data: { email, password, role } });
  assert.equal(result.status, 200, JSON.stringify(result.body));
  return result.body.token;
};

test('PostgreSQL API persistence, authorization, traceability, and import behavior', async () => {
  const db = createPool({ connectionString: databaseUrl });
  let server = await startServer();
  try {
    const firstId = `patient-a-${runId}`;
    const secondId = `patient-b-${runId}`;
    const register = async (id, doctorId = 'DR-001') => {
      const result = await request('auth/bridge', { method: 'POST', data: { account: {
        id, role: 'patient', email: `${id}@example.test`, password: 'test-password',
        patientProfile: { fullName: id, age: '30', weight: '70', height: '170', diabetesType: 'Type 1 Diabetes', selectedDoctorId: doctorId },
      } } });
      assert.equal(result.status, 200, JSON.stringify(result.body));
      return result.body.token;
    };
    const first = await register(firstId);
    const second = await register(secondId);
    const forbiddenDoctor = await request('auth/bridge', { method: 'POST', data: { account: {
      id: `doctor-${runId}`, role: 'doctor', email: `doctor-${runId}@example.test`, password: 'test-password', doctorProfile: { fullName: 'Unprovisioned Doctor' },
    } } });
    assert.equal(forbiddenDoctor.status, 403);
    const collidingId = await request('auth/bridge', { method: 'POST', data: { account: {
      id: firstId, role: 'patient', email: `different-${runId}@example.test`, password: 'test-password', patientProfile: { fullName: 'Collision' },
    } } });
    assert.equal(collidingId.status, 409);
    const doctorOne = await login('sarah.ahmed@clinic.example', 'password', 'doctor');
    const doctorTwo = await login('khaled.mansour@clinic.example', 'password', 'doctor');
    assert.equal((await request('assignment', { token: doctorTwo, method: 'POST', data: { patientId: firstId, status: 'accepted' } })).status, 400);
    assert.equal((await request('assignment', { token: doctorOne, method: 'POST', data: { patientId: firstId, status: 'accepted' } })).status, 200);
    assert.equal((await request('rating', { token: first, method: 'POST', data: { doctorId: 'DR-001', score: 5 } })).status, 200);
    assert.equal((await request('rating', { token: doctorOne, method: 'POST', data: { doctorId: 'DR-001', score: 5 } })).status, 403);

    const reading = { id: `reading-${runId}`, patientSlug: firstId, value: 120, recordedAt: new Date().toISOString() };
    assert.equal((await request('glucose', { token: first, method: 'POST', data: reading })).status, 200);
    assert.equal((await request('glucose', { token: first, method: 'POST', data: reading })).status, 200);
    assert.equal((await request('glucose', { token: first, method: 'POST', data: { ...reading, value: 121 } })).status, 409);
    assert.equal((await request('glucose', { token: second, method: 'POST', data: { ...reading, patientSlug: firstId } })).status, 403);

    const plannedMealId = `meal-planned-${runId}`;
    const zeroMealId = `meal-zero-${runId}`;
    assert.equal((await request('food', { token: first, method: 'POST', data: {
      id: plannedMealId, patientSlug: firstId, announcedCarbsG: 30, status: 'planned', plannedEatingAt: new Date().toISOString(),
    } })).status, 200);
    assert.equal((await request('food', { token: first, method: 'POST', data: {
      id: zeroMealId, patientSlug: firstId, announcedCarbsG: 0, consumedCarbsG: 0, status: 'eaten',
      plannedEatingAt: new Date().toISOString(), actualEatingAt: new Date().toISOString(),
    } })).status, 200);
    const meals = await db.query('SELECT id,consumed_carbs_g FROM meals WHERE id=ANY($1::text[]) ORDER BY id', [[plannedMealId, zeroMealId]]);
    assert.equal(meals.rows.find((row) => row.id === plannedMealId).consumed_carbs_g, null);
    assert.equal(Number(meals.rows.find((row) => row.id === zeroMealId).consumed_carbs_g), 0);

    const contactOne = await request('emergency-contacts', { token: first, method: 'POST', data: { contactName: 'One', relationship: 'Parent', phoneNumber: '+201111111111', isPrimary: true } });
    assert.equal(contactOne.status, 201);
    const contactTwo = await request('emergency-contacts', { token: first, method: 'POST', data: { contactName: 'Two', relationship: 'Sibling', phoneNumber: '+202222222222', isPrimary: true } });
    assert.equal(contactTwo.status, 201);
    const contacts = (await request('emergency-contacts', { token: first })).body.contacts;
    assert.equal(contacts.length, 2);
    assert.equal(contacts.filter((contact) => contact.isPrimary).length, 1);
    assert.equal(contacts.find((contact) => contact.isPrimary).contactName, 'Two');

    const messageOne = { id: `message-old-${runId}`, patientSlug: firstId, from: 'patient', text: 'Old doctor conversation' };
    assert.equal((await request('messages', { token: first, method: 'POST', data: messageOne })).status, 200);
    assert.equal((await request('patient/doctor-request', { token: first, method: 'POST', data: { doctorId: 'DR-002' } })).status, 200);
    assert.equal((await request('snapshot', { token: doctorOne })).body.messages.some((item) => item.id === messageOne.id), false);
    assert.equal((await request('snapshot', { token: doctorTwo })).body.messages.some((item) => item.id === messageOne.id), false);
    assert.equal((await request('assignment', { token: doctorTwo, method: 'POST', data: { patientId: firstId, status: 'accepted' } })).status, 200);
    const messageTwo = { id: `message-new-${runId}`, patientSlug: firstId, from: 'patient', text: 'New doctor conversation' };
    assert.equal((await request('messages', { token: first, method: 'POST', data: messageTwo })).status, 200);
    assert.equal((await request('snapshot', { token: doctorTwo })).body.messages.some((item) => item.id === messageTwo.id), true);
    assert.equal((await request('snapshot', { token: doctorTwo })).body.messages.some((item) => item.id === messageOne.id), false);

    await stopServer(server);
    server = null;
    server = await startServer();
    const afterRestart = await login(`${firstId}@example.test`, 'test-password');
    assert.equal((await request('snapshot', { token: afterRestart })).body.glucose.some((item) => item.id === reading.id), true);

    const predictionId = `prediction-${runId}`;
    const recommendationId = `recommendation-${runId}`;
    await db.query(`INSERT INTO predictions(id,patient_id,requested_by_user_id,forecast_origin_at,input_snapshot,input_snapshot_sha256,status)
      VALUES($1,$2,$2,now(),'{}','test-hash','completed')`, [predictionId, firstId]);
    await db.query(`INSERT INTO recommendations(id,patient_id,prediction_id,recommendation_type,suggested_amount,suggested_unit,validation_status)
      VALUES($1,$2,$3,'bolus',2,'U','unavailable')`, [recommendationId, firstId, predictionId]);
    await db.query(`INSERT INTO recommendation_responses(id,recommendation_id,patient_id,response)
      VALUES($1,$2,$3,'accepted')`, [`response-${runId}`, recommendationId, firstId]);
    assert.equal(Number((await db.query('SELECT count(*) FROM insulin_doses WHERE recommendation_id=$1', [recommendationId])).rows[0].count), 0);
    assert.equal(Number((await db.query('SELECT count(*) FROM meals WHERE recommendation_id=$1', [recommendationId])).rows[0].count), 0);
    await assert.rejects(db.query(`INSERT INTO insulin_doses(id,patient_id,administered_units,administered_at,decision_source,recommendation_id)
      VALUES($1,$2,1,now(),'ai_followed',$3)`, [`wrong-dose-${runId}`, secondId, recommendationId]));

    const directory = await mkdtemp(join(tmpdir(), 'glucotwin-import-'));
    const importId = `imported-${runId}`;
    const fixture = join(directory, 'data.json');
    await writeFile(fixture, JSON.stringify({
      accounts: [{ id: importId, role: 'patient', email: `${importId}@example.test`, passwordHash: passwordHash('import-password'), patientProfile: { fullName: 'Imported Patient' } }],
      assignments: [], food: [], bolus: [], glucose: [], messages: [], ratings: [],
    }));
    for (let pass = 0; pass < 2; pass++) {
      const imported = spawn(process.execPath, [importFile, fixture], { env: { ...process.env, DATABASE_URL: databaseUrl } });
      assert.equal(await new Promise((resolve) => imported.once('exit', resolve)), 0);
    }
    assert.equal(Number((await db.query('SELECT count(*) FROM users WHERE id=$1', [importId])).rows[0].count), 1);
  } finally {
    if (server) await stopServer(server);
    await db.end();
  }
});
