import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

test('mobile and website roles share only assigned patient records', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'glucotwin-sync-'));
  const port = 40000 + Math.floor(Math.random() * 10000);
  const server = spawn(process.execPath, [fileURLToPath(new URL('./index.mjs', import.meta.url))], {
    env: { ...process.env, SYNC_PORT: String(port), SYNC_DATA_FILE: join(directory, 'data.json') },
    stdio: 'ignore',
  });
  const url = `http://127.0.0.1:${port}/api/`;
  const request = async (path, token, data) => {
    const response = await fetch(url + path, {
      method: data ? 'POST' : 'GET',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: data ? JSON.stringify(data) : undefined,
    });
    return { status: response.status, body: await response.json() };
  };
  try {
    for (let attempt = 0; attempt < 40; attempt++) {
      try { await request('doctors'); break; }
      catch { await new Promise((resolve) => setTimeout(resolve, 100)); }
    }
    const register = async (id) => {
      const result = await request('auth/bridge', null, { account: {
        id, role: 'patient', email: `${id}@example.test`, password: 'test-password',
        patientProfile: { fullName: id, age: '30', weight: '70', height: '170', diabetesType: 'Type 1 Diabetes', selectedDoctorId: 'DR-001' },
      } });
      assert.equal(result.status, 200);
      return result.body.token;
    };
    const first = await register('test-one');
    const second = await register('test-two');
    const doctor = (await request('auth/bridge', null, { account: { id: 'DR-001', role: 'doctor', email: 'sarah.ahmed@clinic.example', password: 'password', doctorProfile: { fullName: 'Dr. Sarah Ahmed' } } })).body.token;
    assert.equal((await request('assignment', doctor, { patientId: 'test-one', status: 'accepted' })).status, 200);
    assert.equal((await request('glucose', first, { id: 'reading-1', patientSlug: 'test-one', value: 120, time: '12:00', recordedAt: new Date().toISOString() })).status, 200);
    assert.equal((await request('food', first, { id: 'food-1', patientSlug: 'test-one', meal: 'Lunch', items: 'Soup', carbs: '20g' })).status, 200);
    assert.equal((await request('bolus', first, { id: 'bolus-1', patientSlug: 'test-one', meal: 'Lunch', recorded: '2 U' })).status, 200);
    assert.equal((await request('messages', first, { id: 'message-1', patientSlug: 'test-one', from: 'patient', text: 'Hello' })).status, 200);
    assert.equal((await request('glucose', second, { id: 'bad-reading', patientSlug: 'test-one', value: 200 })).status, 403);
    assert.equal((await request('rating', first, { doctorId: 'DR-001', score: 5 })).status, 200);
    assert.equal((await request('rating', second, { doctorId: 'DR-001', score: 9 })).status, 400);
    assert.equal((await request('rating', doctor, { doctorId: 'DR-001', score: 5 })).status, 403);
    const doctorDirectory = (await request('doctors')).body;
    assert.equal(doctorDirectory.doctors.find((item) => item.id === 'DR-001').rating.average, 5);
    assert.ok(doctorDirectory.ratings.every((item) => item.patientId === ''));
    const firstSnapshot = (await request('snapshot', first)).body;
    const secondSnapshot = (await request('snapshot', second)).body;
    const doctorSnapshot = (await request('snapshot', doctor)).body;
    assert.equal(firstSnapshot.glucose.length, 1);
    assert.equal(secondSnapshot.glucose.length, 0);
    assert.equal(doctorSnapshot.glucose.filter((item) => item.patientSlug === 'test-one').length, 1);
    assert.equal(doctorSnapshot.food.filter((item) => item.patientSlug === 'test-one').length, 1);
    assert.equal(doctorSnapshot.bolus.filter((item) => item.patientSlug === 'test-one').length, 1);
    assert.equal(doctorSnapshot.messages.filter((item) => item.patientSlug === 'test-one').length, 1);
    assert.ok(firstSnapshot.ratings.some((item) => item.patientId === 'test-one'));
    assert.ok(secondSnapshot.ratings.every((item) => item.patientId !== 'test-one'));
    assert.equal(firstSnapshot.demo, null);
    assert.equal(secondSnapshot.demo, null);
    assert.equal(secondSnapshot.food.length, 0);
    const demoToken = (await request('auth/login', null, { email: 'omar.hassan@example.com', password: 'password' })).body.token;
    const demoSnapshot = (await request('snapshot', demoToken)).body;
    const fixture = JSON.parse(readFileSync(new URL('../../apps/web/src/data/demoPatient.json', import.meta.url), 'utf8'));
    assert.deepEqual(demoSnapshot.demo.cgm, fixture.cgm);
    assert.deepEqual(demoSnapshot.demo.forecast, fixture.forecast);
    assert.equal(demoSnapshot.food.length, 4);
    assert.equal(demoSnapshot.bolus.length, 3);
    assert.equal(demoSnapshot.glucose.length, 2);
    assert.equal(demoSnapshot.messages.length, 2);
    assert.deepEqual(doctorSnapshot.messages.filter((item) => item.patientSlug === 'omar-hassan'), demoSnapshot.messages);
    assert.equal((await request('snapshot')).status, 401);
    const newDoctor = (await request('auth/login', null, { email: 'khaled.mansour@clinic.example', password: 'password', role: 'doctor' })).body.token;
    assert.equal((await request('patient/doctor-request', doctor, { doctorId: 'DR-002' })).status, 403);
    assert.equal((await request('patient/doctor-request', first, { doctorId: 'missing' })).status, 400);
    assert.equal((await request('patient/doctor-request', first, { doctorId: 'DR-002' })).status, 200);
    const pending = (await request('snapshot', newDoctor)).body;
    assert.equal(pending.assignments[0].status, 'pending');
    assert.equal(pending.messages.length, 0);
    assert.equal((await request('snapshot', doctor)).body.messages.filter((item) => item.patientSlug === 'test-one').length, 0);
    assert.equal((await request('messages', first, { id: 'pending-message', patientSlug: 'test-one', from: 'patient', text: 'Not yet' })).status, 403);
    assert.equal((await request('assignment', newDoctor, { patientId: 'test-one', status: 'accepted' })).status, 200);
    assert.equal((await request('messages', first, { id: 'new-doctor-message', patientSlug: 'test-one', from: 'patient', text: 'Demo connection test' })).status, 200);
    assert.deepEqual((await request('snapshot', newDoctor)).body.messages.map((item) => item.id), ['new-doctor-message']);
    assert.deepEqual((await request('snapshot', first)).body.messages.map((item) => item.id), ['new-doctor-message']);
  } finally { server.kill(); }
});
