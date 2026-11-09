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
const localSyncMetadata = { syncState: 'pending', syncAttempts: 2, syncNextAttemptAt: 1234, syncError: 'offline' };
const assertNoLocalSyncMetadata = (value) => {
  for (const field of Object.keys(localSyncMetadata)) assert.equal(Object.hasOwn(value, field), false, `${field} leaked from the API`);
};

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
      assert.equal(result.body.assignment.status, 'pending');
      assert.equal(result.body.assignment.doctorId, doctorId);
      return result.body.token;
    };
    const first = await register(firstId);
    const second = await register(secondId);
    const bridgeProfile = async (account, password = 'test-password') => request('auth/bridge', {
      method: 'POST', data: { account: { ...account, password } },
    });
    let roundTripAccount = (await request('snapshot', { token: first })).body.account;
    assert.equal(roundTripAccount.patientProfile.diagnosisYear, '');
    for (let pass = 0; pass < 2; pass++) {
      const roundTrip = await bridgeProfile(roundTripAccount);
      assert.equal(roundTrip.status, 200, JSON.stringify(roundTrip.body));
      roundTripAccount = roundTrip.body.account;
      assert.equal(roundTripAccount.patientProfile.diagnosisYear, '');
    }
    let profileUpdate = await bridgeProfile({ ...roundTripAccount, patientProfile: {
      ...roundTripAccount.patientProfile, age: ' ', weight: '', height: '\t', diagnosisYear: '',
    } });
    assert.equal(profileUpdate.status, 200, JSON.stringify(profileUpdate.body));
    assert.deepEqual((await db.query('SELECT age_years,weight_kg,height_cm,diagnosis_year FROM patient_profiles WHERE user_id=$1', [firstId])).rows[0], {
      age_years: null, weight_kg: null, height_cm: null, diagnosis_year: null,
    });
    profileUpdate = await bridgeProfile({ ...profileUpdate.body.account, patientProfile: {
      ...profileUpdate.body.account.patientProfile, age: '0', weight: 0, height: '0', diagnosisYear: 0,
    } });
    assert.equal(profileUpdate.status, 200, JSON.stringify(profileUpdate.body));
    assert.deepEqual((await db.query('SELECT age_years,weight_kg,height_cm,diagnosis_year FROM patient_profiles WHERE user_id=$1', [firstId])).rows[0], {
      age_years: 0, weight_kg: '0', height_cm: '0', diagnosis_year: 0,
    });
    profileUpdate = await bridgeProfile({ ...profileUpdate.body.account, patientProfile: {
      ...profileUpdate.body.account.patientProfile, age: '31', weight: '71', height: '171', diagnosisYear: '2010',
    } });
    assert.equal(profileUpdate.status, 200, JSON.stringify(profileUpdate.body));
    const { age: omittedAge, weight: omittedWeight, height: omittedHeight, diagnosisYear: omittedDiagnosisYear, ...profileWithoutNumbers } = profileUpdate.body.account.patientProfile;
    void omittedAge; void omittedWeight; void omittedHeight; void omittedDiagnosisYear;
    profileUpdate = await bridgeProfile({ ...profileUpdate.body.account, patientProfile: profileWithoutNumbers });
    assert.equal(profileUpdate.status, 200, JSON.stringify(profileUpdate.body));
    assert.deepEqual((await db.query('SELECT age_years,weight_kg,height_cm,diagnosis_year FROM patient_profiles WHERE user_id=$1', [firstId])).rows[0], {
      age_years: 31, weight_kg: '71', height_cm: '171', diagnosis_year: 2010,
    });
    for (const [field, invalid] of [['age', -1], ['weight', false], ['height', 'bad'], ['diagnosisYear', 'Infinity']]) {
      const invalidProfile = await bridgeProfile({ ...profileUpdate.body.account, patientProfile: { ...profileUpdate.body.account.patientProfile, [field]: invalid } });
      assert.equal(invalidProfile.status, 400, `accepted invalid profile ${field}`);
    }
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
    const doctorThreeLogin = await request('auth/login', { method: 'POST', data: { email: 'reem.osman@clinic.example', password: 'password', role: 'doctor' } });
    const doctorThree = doctorThreeLogin.body.token;
    const doctorAccount = doctorThreeLogin.body.account;
    let doctorProfileUpdate = await bridgeProfile({ ...doctorAccount, doctorProfile: { ...doctorAccount.doctorProfile, yearsExperience: ' ' } }, 'password');
    assert.equal(doctorProfileUpdate.status, 200, JSON.stringify(doctorProfileUpdate.body));
    assert.equal((await db.query("SELECT years_experience FROM doctor_profiles WHERE user_id='DR-003'")).rows[0].years_experience, null);
    doctorProfileUpdate = await bridgeProfile({ ...doctorProfileUpdate.body.account, doctorProfile: { ...doctorProfileUpdate.body.account.doctorProfile, yearsExperience: 0 } }, 'password');
    assert.equal(doctorProfileUpdate.status, 200);
    assert.equal((await db.query("SELECT years_experience FROM doctor_profiles WHERE user_id='DR-003'")).rows[0].years_experience, 0);
    doctorProfileUpdate = await bridgeProfile({ ...doctorProfileUpdate.body.account, doctorProfile: { ...doctorProfileUpdate.body.account.doctorProfile, yearsExperience: 10 } }, 'password');
    assert.equal(doctorProfileUpdate.status, 200, JSON.stringify(doctorProfileUpdate.body));
    const { yearsExperience: omittedExperience, ...doctorWithoutExperience } = doctorProfileUpdate.body.account.doctorProfile;
    void omittedExperience;
    doctorProfileUpdate = await bridgeProfile({ ...doctorProfileUpdate.body.account, doctorProfile: doctorWithoutExperience }, 'password');
    assert.equal(doctorProfileUpdate.status, 200);
    assert.equal((await db.query("SELECT years_experience FROM doctor_profiles WHERE user_id='DR-003'")).rows[0].years_experience, 10);
    assert.equal((await bridgeProfile({ ...doctorProfileUpdate.body.account, doctorProfile: { ...doctorProfileUpdate.body.account.doctorProfile, yearsExperience: false } }, 'password')).status, 400);

    const journeyId = `journey-${runId}`;
    const journey = await register(journeyId);
    assert.equal(Number((await db.query('SELECT count(*) FROM care_assignments WHERE patient_id=$1', [journeyId])).rows[0].count), 1);
    assert.equal((await request('snapshot', { token: doctorOne })).body.assignments.some((item) => item.patientId === journeyId && item.status === 'pending'), true);
    const declinedJourney = await request('assignment', { token: doctorOne, method: 'POST', data: { patientId: journeyId, status: 'declined' } });
    assert.equal(declinedJourney.status, 200);
    assert.equal(declinedJourney.body.assignment.status, 'declined');
    assert.equal((await request('assignment', { token: doctorOne, method: 'POST', data: { patientId: journeyId, status: 'declined' } })).status, 200);
    assert.equal((await request('assignment', { token: doctorTwo, method: 'POST', data: { patientId: journeyId, status: 'accepted' } })).status, 400);
    assert.equal(Number((await db.query('SELECT count(*) FROM conversations WHERE patient_id=$1', [journeyId])).rows[0].count), 0);

    const journeyLogin = await request('auth/login', { method: 'POST', data: { email: `${journeyId}@example.test`, password: 'test-password', role: 'patient' } });
    assert.equal(journeyLogin.status, 200);
    assert.equal((await request('snapshot', { token: journeyLogin.body.token })).body.assignments.find((item) => item.doctorId === 'DR-001').status, 'declined');
    assert.equal(Number((await db.query('SELECT count(*) FROM care_assignments WHERE patient_id=$1', [journeyId])).rows[0].count), 1);

    const journeyRoundTrip = await request('auth/bridge', { method: 'POST', data: { account: {
      ...journeyLogin.body.account, password: 'test-password',
      patientProfile: { ...journeyLogin.body.account.patientProfile, fullName: 'Profile Edited Without Request' },
    } } });
    assert.equal(journeyRoundTrip.status, 200, JSON.stringify(journeyRoundTrip.body));
    assert.equal(journeyRoundTrip.body.assignment, null);
    const journeyProfile = await request('profile', { token: journey, method: 'PUT', data: { profile: {
      ...journeyRoundTrip.body.account.patientProfile, medications: 'Profile-only edit',
    } } });
    assert.equal(journeyProfile.status, 200, JSON.stringify(journeyProfile.body));
    assert.equal(Number((await db.query('SELECT count(*) FROM care_assignments WHERE patient_id=$1', [journeyId])).rows[0].count), 1);

    const retriedJourney = await request('patient/doctor-request', { token: journey, method: 'POST', data: { doctorId: 'DR-001' } });
    assert.equal(retriedJourney.status, 200);
    assert.equal(retriedJourney.body.assignment.status, 'pending');
    assert.equal(Number((await db.query('SELECT count(*) FROM care_assignments WHERE patient_id=$1', [journeyId])).rows[0].count), 2);
    assert.equal((await request('patient/doctor-request', { token: journey, method: 'POST', data: { doctorId: 'DR-001' } })).body.assignment.id, retriedJourney.body.assignment.id);
    assert.equal(Number((await db.query('SELECT count(*) FROM care_assignments WHERE patient_id=$1', [journeyId])).rows[0].count), 2);

    const switchedJourney = await request('patient/doctor-request', { token: journey, method: 'POST', data: { doctorId: 'DR-002' } });
    assert.equal(switchedJourney.status, 200);
    const journeyHistory = (await db.query('SELECT doctor_id,status FROM care_assignments WHERE patient_id=$1', [journeyId])).rows;
    assert.deepEqual(journeyHistory.map((item) => `${item.doctor_id}:${item.status}`).sort(), ['DR-001:declined', 'DR-001:ended', 'DR-002:pending']);

    const publicBio = `Updated public biography ${runId}`;
    const profileSaved = await request('profile', { token: doctorThree, method: 'PUT', data: { profile: {
      ...doctorProfileUpdate.body.account.doctorProfile, bio: publicBio, fullName: 'Dr. Reem Osman Updated',
    } } });
    assert.equal(profileSaved.status, 200, JSON.stringify(profileSaved.body));
    assert.equal(profileSaved.body.account.doctorProfile.bio, publicBio);
    const publicDoctor = (await request('doctors')).body.doctors.find((item) => item.id === 'DR-003');
    assert.equal(publicDoctor.doctorProfile.bio, publicBio);
    assert.equal(publicDoctor.doctorProfile.fullName, 'Dr. Reem Osman Updated');
    assert.equal(Object.hasOwn(publicDoctor, 'password'), false);

    assert.equal((await request('assignment', { token: doctorTwo, method: 'POST', data: { patientId: firstId, status: 'accepted' } })).status, 400);
    assert.equal((await request('assignment', { token: doctorOne, method: 'POST', data: { patientId: firstId, status: 'accepted' } })).status, 200);
    assert.equal((await request('rating', { token: first, method: 'POST', data: { doctorId: 'DR-001', score: 5 } })).status, 200);
    assert.equal((await request('rating', { token: doctorOne, method: 'POST', data: { doctorId: 'DR-001', score: 5 } })).status, 403);

    const reading = { id: `reading-${runId}`, patientSlug: firstId, value: 120, recordedAt: '2026-01-01T13:10:00Z', ...localSyncMetadata };
    assert.equal((await request('glucose', { token: first, method: 'POST', data: reading })).status, 200);
    assertNoLocalSyncMetadata((await db.query('SELECT legacy_payload FROM glucose_readings WHERE id=$1', [reading.id])).rows[0].legacy_payload);
    assert.equal((await request('glucose', { token: first, method: 'POST', data: { ...reading, recordedAt: '2026-01-01T13:10:00.000Z', time: 'display only' } })).status, 200);
    const concurrentId = `reading-concurrent-${runId}`;
    const concurrent = { ...reading, id: concurrentId };
    assert.deepEqual((await Promise.all([
      request('glucose', { token: first, method: 'POST', data: concurrent }),
      request('glucose', { token: first, method: 'POST', data: { ...concurrent, recordedAt: '2026-01-01T13:10:00.000Z' } }),
    ])).map((result) => result.status), [200, 200]);
    assert.equal(Number((await db.query('SELECT count(*) FROM glucose_readings WHERE id=$1', [concurrentId])).rows[0].count), 1);
    assert.equal((await request('glucose', { token: first, method: 'POST', data: { ...reading, value: 121 } })).status, 409);
    assert.equal((await request('glucose', { token: second, method: 'POST', data: { ...reading, patientSlug: firstId } })).status, 403);
    await db.query('UPDATE glucose_readings SET legacy_payload=legacy_payload || $2::jsonb WHERE id=$1', [reading.id, JSON.stringify(localSyncMetadata)]);
    assertNoLocalSyncMetadata((await request('snapshot', { token: first })).body.glucose.find((item) => item.id === reading.id));

    const plannedMealId = `meal-planned-${runId}`;
    const legacyPlannedMealId = `meal-legacy-${runId}`;
    const zeroMealId = `meal-zero-${runId}`;
    assert.equal((await request('food', { token: first, method: 'POST', data: {
      id: plannedMealId, patientSlug: firstId, announcedCarbsG: 30, status: 'planned', plannedEatingAt: new Date().toISOString(), ...localSyncMetadata,
    } })).status, 200);
    assertNoLocalSyncMetadata((await db.query('SELECT legacy_payload FROM meals WHERE id=$1', [plannedMealId])).rows[0].legacy_payload);
    const legacyTime = '2026-01-02T10:00:00.000Z';
    assert.equal((await request('food', { token: first, method: 'POST', data: {
      id: legacyPlannedMealId, patientSlug: firstId, carbs: '45g', status: 'planned', plannedEatingAt: legacyTime,
    } })).status, 200);
    assert.equal((await request('food', { token: first, method: 'POST', data: {
      id: legacyPlannedMealId, patientSlug: firstId, carbs: '45g', status: 'planned', plannedEatingAt: legacyTime.replace('.000Z', 'Z'), time: 'display only',
    } })).status, 200);
    assert.equal((await request('food', { token: first, method: 'POST', data: {
      id: zeroMealId, patientSlug: firstId, announcedCarbsG: 0, consumedCarbsG: 0, status: 'eaten',
      plannedEatingAt: new Date().toISOString(), actualEatingAt: new Date().toISOString(),
    } })).status, 200);
    const meals = await db.query('SELECT id,consumed_carbs_g FROM meals WHERE id=ANY($1::text[]) ORDER BY id', [[plannedMealId, zeroMealId]]);
    assert.equal(meals.rows.find((row) => row.id === plannedMealId).consumed_carbs_g, null);
    assert.equal(Number(meals.rows.find((row) => row.id === zeroMealId).consumed_carbs_g), 0);
    assert.equal((await db.query('SELECT consumed_carbs_g FROM meals WHERE id=$1', [legacyPlannedMealId])).rows[0].consumed_carbs_g, null);
    await db.query('UPDATE meals SET legacy_payload=legacy_payload || $2::jsonb WHERE id=$1', [plannedMealId, JSON.stringify(localSyncMetadata)]);
    assertNoLocalSyncMetadata((await request('snapshot', { token: first })).body.food.find((item) => item.id === plannedMealId));

    const confirmed = await request(`food/${plannedMealId}`, { token: first, method: 'PATCH', data: {
      expectedVersion: 1, mutationId: `confirm-${runId}`, status: 'eaten', actualEatingAt: legacyTime, confirmAnnouncedAmount: true,
    } });
    assert.equal(confirmed.status, 200, JSON.stringify(confirmed.body));
    assert.equal(confirmed.body.meal.version, 2);
    assert.equal(confirmed.body.meal.consumedCarbsG, 30);
    assert.equal((await request(`food/${plannedMealId}`, { token: first, method: 'PATCH', data: {
      expectedVersion: 1, mutationId: `confirm-${runId}`, status: 'eaten', actualEatingAt: legacyTime, confirmAnnouncedAmount: true,
    } })).status, 200);
    assert.equal((await request(`food/${plannedMealId}`, { token: first, method: 'PATCH', data: {
      expectedVersion: 1, mutationId: `confirm-${runId}`, status: 'eaten', actualEatingAt: legacyTime, consumedCarbsG: 12,
    } })).status, 409);
    assert.equal((await request(`food/${plannedMealId}`, { token: first, method: 'PATCH', data: {
      expectedVersion: 1, mutationId: `stale-${runId}`, status: 'eaten', actualEatingAt: legacyTime, consumedCarbsG: 10,
    } })).status, 409);
    assert.equal((await request(`food/${legacyPlannedMealId}`, { token: second, method: 'PATCH', data: {
      expectedVersion: 1, mutationId: `forbidden-${runId}`, status: 'cancelled',
    } })).status, 403);
    const cancelled = await request(`food/${legacyPlannedMealId}`, { token: first, method: 'PATCH', data: {
      expectedVersion: 1, mutationId: `cancel-${runId}`, status: 'cancelled',
    } });
    assert.equal(cancelled.status, 200);
    assert.equal(cancelled.body.meal.consumedCarbsG, null);
    assert.equal((await request('food', { token: first, method: 'POST', data: {
      id: legacyPlannedMealId, patientSlug: firstId, carbs: '45g', status: 'planned', plannedEatingAt: legacyTime,
    } })).status, 200);
    assert.equal((await request('food', { token: first, method: 'POST', data: {
      id: legacyPlannedMealId, patientSlug: firstId, carbs: '46g', status: 'planned', plannedEatingAt: legacyTime,
    } })).status, 409);
    const snapMeal = (await request('snapshot', { token: first })).body.food.find((item) => item.id === plannedMealId);
    assert.equal(snapMeal.status, 'eaten');
    assert.equal(snapMeal.version, 2);

    for (const invalid of [-1, false, ' ', '1x', 'NaN', 'Infinity']) {
      const invalidResult = await request('food', { token: first, method: 'POST', data: {
        id: `invalid-${String(invalid)}-${runId}`, patientSlug: firstId, announcedCarbsG: invalid,
        status: 'planned', plannedEatingAt: legacyTime,
      } });
      assert.equal(invalidResult.status, 400, `accepted invalid numeric ${String(invalid)}`);
    }
    assert.equal((await request('glucose', { token: first, method: 'POST', data: {
      id: `blank-glucose-${runId}`, patientSlug: firstId, value: ' ', recordedAt: legacyTime,
    } })).status, 400);
    assert.equal((await request('bolus', { token: first, method: 'POST', data: {
      id: `blank-bolus-${runId}`, patientSlug: firstId, recorded: ' ', administeredAt: legacyTime,
    } })).status, 400);
    assert.equal((await request('glucose', { token: first, method: 'POST', data: {
      id: `no-zone-${runId}`, patientSlug: firstId, value: 100, recordedAt: '2026-01-01T10:00:00',
    } })).status, 400);
    assert.equal((await request('bolus', { token: first, method: 'POST', data: {
      id: `bolus-${runId}`, patientSlug: firstId, recorded: '2 U', administeredAt: legacyTime, ...localSyncMetadata,
    } })).status, 200);
    assert.equal((await request('bolus', { token: first, method: 'POST', data: {
      id: `bolus-${runId}`, patientSlug: firstId, administeredUnits: 2, administeredAt: legacyTime.replace('.000Z', 'Z'), time: 'display only',
    } })).status, 200);
    assert.equal((await db.query('SELECT administered_at FROM insulin_doses WHERE id=$1', [`bolus-${runId}`])).rows[0].administered_at.toISOString(), legacyTime);
    assertNoLocalSyncMetadata((await db.query('SELECT legacy_payload FROM insulin_doses WHERE id=$1', [`bolus-${runId}`])).rows[0].legacy_payload);
    await db.query('UPDATE insulin_doses SET legacy_payload=legacy_payload || $2::jsonb WHERE id=$1', [`bolus-${runId}`, JSON.stringify(localSyncMetadata)]);
    assertNoLocalSyncMetadata((await request('snapshot', { token: first })).body.bolus.find((item) => item.id === `bolus-${runId}`));

    const contactOne = await request('emergency-contacts', { token: first, method: 'POST', data: { contactName: 'One', relationship: 'Parent', phoneNumber: '+201111111111', isPrimary: true } });
    assert.equal(contactOne.status, 201);
    const contactTwo = await request('emergency-contacts', { token: first, method: 'POST', data: { contactName: 'Two', relationship: 'Sibling', phoneNumber: '+202222222222', isPrimary: true } });
    assert.equal(contactTwo.status, 201);
    const contacts = (await request('emergency-contacts', { token: first })).body.contacts;
    assert.equal(contacts.length, 2);
    assert.equal(contacts.filter((contact) => contact.isPrimary).length, 1);
    assert.equal(contacts.find((contact) => contact.isPrimary).contactName, 'Two');
    assert.equal((await request(`emergency-contacts/${contactOne.body.contact.id}`, { token: first, method: 'PUT', data: { contactName: 'One Updated', phoneNumber: '+201111111112', isPrimary: true } })).status, 200);
    const changedContacts = (await request('emergency-contacts', { token: first })).body.contacts;
    assert.equal(changedContacts.filter((contact) => contact.isPrimary).length, 1);
    assert.equal(changedContacts.find((contact) => contact.isPrimary).contactName, 'One Updated');
    assert.equal((await request('emergency-contacts', { token: first, method: 'POST', data: { contactName: 'Bad', relationship: 'Friend', phoneNumber: '01001234567' } })).status, 400);
    assert.equal((await request(`emergency-contacts/${contactOne.body.contact.id}`, { token: second, method: 'PUT', data: { relationship: 'Other' } })).status, 404);
    assert.equal((await request(`emergency-contacts/${contactOne.body.contact.id}`, { token: second, method: 'DELETE' })).status, 404);
    assert.equal((await request(`emergency-contacts/${contactTwo.body.contact.id}`, { token: first, method: 'DELETE' })).status, 200);
    assert.equal((await request('emergency-contacts', { token: first })).body.contacts.length, 1);

    const messageOne = { id: `message-old-${runId}`, patientSlug: firstId, from: 'patient', text: 'Old doctor conversation', sentAt: '2026-01-01T13:10:00Z', ...localSyncMetadata };
    assert.equal((await request('messages', { token: first, method: 'POST', data: messageOne })).status, 200);
    assert.equal((await request('messages', { token: first, method: 'POST', data: { ...messageOne, sentAt: '2026-01-01T13:10:00.000Z', time: 'Now' } })).status, 200);
    assertNoLocalSyncMetadata((await db.query('SELECT legacy_payload FROM messages WHERE id=$1', [messageOne.id])).rows[0].legacy_payload);
    await db.query('UPDATE messages SET legacy_payload=legacy_payload || $2::jsonb WHERE id=$1', [messageOne.id, JSON.stringify(localSyncMetadata)]);
    assertNoLocalSyncMetadata((await request('snapshot', { token: first })).body.messages.find((item) => item.id === messageOne.id));
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
    const importMealId = `imported-meal-${runId}`;
    const importRatingId = `imported-rating-${runId}`;
    const fixture = join(directory, 'data.json');
    await writeFile(fixture, JSON.stringify({
      accounts: [{ id: importId, role: 'patient', email: `${importId}@example.test`, passwordHash: passwordHash('import-password'), patientProfile: { fullName: 'Imported Patient' } }],
      assignments: [], food: [{ id: importMealId, patientSlug: importId, meal: 'Legacy meal', items: 'Unknown',
        carbs: '20g', status: 'Recorded', plannedEatingAt: '2026-06-01T12:00:00+02:00', ...localSyncMetadata }],
      bolus: [], glucose: [], messages: [], ratings: [{ id: importRatingId, doctorId: 'DR-001', patientId: null, score: 4, source: 'imported' }],
    }));
    for (let pass = 0; pass < 2; pass++) {
      const imported = spawn(process.execPath, [importFile, fixture], { env: { ...process.env, DATABASE_URL: databaseUrl } });
      assert.equal(await new Promise((resolve) => imported.once('exit', resolve)), 0);
    }
    assert.equal(Number((await db.query('SELECT count(*) FROM users WHERE id=$1', [importId])).rows[0].count), 1);
    const importedMeal = (await db.query('SELECT status,actual_eating_at,consumed_carbs_g,confirmation_provenance,legacy_payload FROM meals WHERE id=$1', [importMealId])).rows[0];
    assert.equal(importedMeal.status, 'planned');
    assert.equal(importedMeal.actual_eating_at, null);
    assert.equal(importedMeal.consumed_carbs_g, null);
    assert.equal(importedMeal.confirmation_provenance.source, 'ambiguous_legacy_import_requires_review');
    assertNoLocalSyncMetadata(importedMeal.legacy_payload);
    const importedRating = (await db.query('SELECT patient_id,source FROM doctor_ratings WHERE id=$1', [importRatingId])).rows[0];
    assert.equal(importedRating.patient_id, null);
    assert.equal(importedRating.source, 'imported');
  } finally {
    if (server) await stopServer(server);
    await db.end();
  }
});
