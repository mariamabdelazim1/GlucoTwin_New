import { createServer } from 'node:http';
import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertDatabaseReady, createPool, withTransaction } from './db.mjs';
import { ApiError, passwordHash, validPassword } from './lib.mjs';
import {
  accountByEmail, accountById, addMessage, addPatientRecord, audit, createEmergencyContact,
  deleteEmergencyContact, doctorDirectory, emergencyContacts, publicAccount, rateDoctor,
  requestDoctor, respondAssignment, snapshot, updateEmergencyContact, updateProfile,
} from './store.mjs';

const serviceDirectory = dirname(fileURLToPath(import.meta.url));
const secretFile = join(serviceDirectory, '.secret');
const secret = process.env.TOKEN_SECRET
  ? Buffer.from(process.env.TOKEN_SECRET)
  : existsSync(secretFile) ? readFileSync(secretFile) : randomBytes(32);
if (!process.env.TOKEN_SECRET && !existsSync(secretFile)) writeFileSync(secretFile, secret, { mode: 0o600 });

const demoPatient = JSON.parse(readFileSync(new URL('../../apps/web/src/data/demoPatient.json', import.meta.url), 'utf8'));
const pool = createPool();

const makeToken = (account) => {
  const payload = Buffer.from(JSON.stringify({ id: account.id, role: account.role, exp: Date.now() + 7 * 86400000 })).toString('base64url');
  return `${payload}.${createHmac('sha256', secret).update(payload).digest('base64url')}`;
};

async function authenticate(req) {
  const [payload, signature] = (req.headers.authorization || '').replace(/^Bearer /, '').split('.');
  if (!payload || !signature) return null;
  const expected = createHmac('sha256', secret).update(payload).digest('base64url');
  if (signature.length !== expected.length || !timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  try {
    const claims = JSON.parse(Buffer.from(payload, 'base64url').toString());
    if (claims.exp <= Date.now()) return null;
    const row = await accountById(pool, claims.id);
    return row && row.role === claims.role ? { id: row.id, role: row.role } : null;
  } catch {
    return null;
  }
}

const reply = (res, status, payload) => {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': process.env.CORS_ORIGIN || '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  });
  res.end(JSON.stringify(payload));
};

const readBody = async (req) => {
  let raw = '';
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 5 * 1024 * 1024) throw new ApiError(413, 'Request too large');
  }
  try { return JSON.parse(raw || '{}'); }
  catch { throw new ApiError(400, 'Invalid JSON request body'); }
};

const contactJson = (row) => ({
  id: row.id, contactName: row.contact_name, relationship: row.relationship,
  phoneNumber: row.phone_number, isPrimary: row.is_primary,
});

const server = createServer(async (req, res) => {
  if (req.method === 'OPTIONS') return reply(res, 204, {});
  try {
    const path = new URL(req.url, 'http://localhost').pathname;
    if (req.method === 'GET' && path === '/api/health') return reply(res, 200, { status: 'ok', database: 'postgresql' });
    if (req.method === 'GET' && path === '/api/doctors') return reply(res, 200, await doctorDirectory(pool));

    if (req.method === 'POST' && path === '/api/auth/bridge') {
      const { account } = await readBody(req);
      if (!account || !['patient', 'doctor'].includes(account.role) || !account.id || !account.email || typeof account.password !== 'string') throw new ApiError(400, 'Invalid account');
      const byEmail = await accountByEmail(pool, account.email);
      const byId = await accountById(pool, account.id);
      if (!byEmail && byId) throw new ApiError(409, 'Account ID is already registered to another identity');
      if (!byEmail && account.role === 'doctor') throw new ApiError(403, 'Doctor accounts must be provisioned by an authorized administrator');
      if (!byEmail && account.password.length < 8) throw new ApiError(400, 'Password must be at least 8 characters');
      if (byEmail && (byEmail.id !== account.id || byEmail.role !== account.role || !validPassword(account.password, byEmail.password_hash))) throw new ApiError(401, 'Account mismatch');
      if (!byEmail) {
        await withTransaction(pool, async (db) => {
          await db.query('INSERT INTO users(id,role,email,password_hash) VALUES($1,$2,$3,$4)', [account.id, account.role, account.email.toLowerCase(), passwordHash(account.password)]);
          await updateProfile(db, account.id, account.role, account.patientProfile || account.doctorProfile);
          await audit(db, account.id, 'account.created', 'user', account.id, { role: account.role });
        });
      } else await withTransaction(pool, async (db) => {
        await updateProfile(db, byEmail.id, byEmail.role, account.patientProfile || account.doctorProfile);
        await audit(db, byEmail.id, 'profile.updated', `${byEmail.role}_profile`, byEmail.id);
      });
      if (account.role === 'patient' && account.patientProfile?.selectedDoctorId) await requestDoctor(pool, account.id, account.patientProfile.selectedDoctorId);
      const stored = await accountById(pool, account.id);
      return reply(res, 200, { token: makeToken(stored), account: publicAccount(stored) });
    }

    if (req.method === 'POST' && path === '/api/auth/login') {
      const input = await readBody(req);
      const role = input.role === 'doctor' ? 'doctor' : 'patient';
      const account = await accountByEmail(pool, input.email || '', role);
      if (!account || !validPassword(String(input.password || ''), account.password_hash)) throw new ApiError(401, 'Incorrect email or password');
      return reply(res, 200, { token: makeToken(account), account: publicAccount(account) });
    }

    const user = await authenticate(req);
    if (!user) throw new ApiError(401, 'Sign in required');

    if (req.method === 'GET' && path === '/api/snapshot') {
      const result = await snapshot(pool, user);
      result.demo = user.role === 'patient' && user.id === demoPatient.patientId
        ? { synthetic: true, summary: demoPatient.summary, cgm: demoPatient.cgm, forecast: demoPatient.forecast, forecastSnapshots: demoPatient.forecastSnapshots }
        : null;
      return reply(res, 200, result);
    }

    if (req.method === 'POST' && path === '/api/assignment') {
      if (user.role !== 'doctor') throw new ApiError(403, 'Doctor access required');
      const input = await readBody(req);
      return reply(res, 200, { assignment: await respondAssignment(pool, user.id, input.patientId, input.status) });
    }
    if (req.method === 'POST' && path === '/api/patient/doctor-request') {
      if (user.role !== 'patient') throw new ApiError(403, 'Patient access required');
      const input = await readBody(req);
      return reply(res, 200, { assignment: await requestDoctor(pool, user.id, input.doctorId) });
    }
    if (req.method === 'POST' && path === '/api/rating') {
      if (user.role !== 'patient') throw new ApiError(403, 'Patient access required');
      const input = await readBody(req);
      return reply(res, 200, { ratings: await rateDoctor(pool, user.id, input.doctorId, input.score) });
    }

    const recordMatch = path.match(/^\/api\/(food|bolus|glucose)$/);
    if (req.method === 'POST' && recordMatch) return reply(res, 200, await addPatientRecord(pool, recordMatch[1], await readBody(req), user));
    if (req.method === 'POST' && path === '/api/messages') return reply(res, 200, await addMessage(pool, await readBody(req), user));

    if (path === '/api/emergency-contacts') {
      if (user.role !== 'patient') throw new ApiError(403, 'Patient access required');
      if (req.method === 'GET') return reply(res, 200, { contacts: await emergencyContacts(pool, user.id) });
      if (req.method === 'POST') return reply(res, 201, { contact: contactJson(await createEmergencyContact(pool, user.id, await readBody(req))) });
    }
    const contactMatch = path.match(/^\/api\/emergency-contacts\/([^/]+)$/);
    if (contactMatch) {
      if (user.role !== 'patient') throw new ApiError(403, 'Patient access required');
      const id = decodeURIComponent(contactMatch[1]);
      if (req.method === 'PUT') return reply(res, 200, { contact: contactJson(await updateEmergencyContact(pool, user.id, id, await readBody(req))) });
      if (req.method === 'DELETE') return reply(res, 200, await deleteEmergencyContact(pool, user.id, id));
    }
    return reply(res, 404, { error: 'Not found' });
  } catch (error) {
    const status = error.status || (error.code === '23505' ? 409 : error.code?.startsWith?.('23') ? 400 : 500);
    if (status === 500) console.error('API request failed:', error.message);
    return reply(res, status, { error: status === 500 ? 'Internal server error' : error.message });
  }
});

try {
  await assertDatabaseReady(pool);
  const port = Number(process.env.SYNC_PORT || 8787);
  const host = process.env.SYNC_HOST || '127.0.0.1';
  server.listen(port, host, () => console.log(`GlucoTwin API listening on ${host}:${port}`));
} catch (error) {
  console.error(`Cannot start GlucoTwin API: ${error.message}`);
  await pool.end();
  process.exitCode = 1;
}

const shutdown = () => server.close(async () => { await pool.end(); process.exit(0); });
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
