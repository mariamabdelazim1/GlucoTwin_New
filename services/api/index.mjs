import { createServer } from 'node:http';
import { createHmac, randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const serviceDirectory = dirname(fileURLToPath(import.meta.url));
const file = process.env.SYNC_DATA_FILE || join(serviceDirectory, 'data.json');
const secretFile = join(dirname(file), '.secret');
mkdirSync(dirname(file), { recursive: true });
const secret = existsSync(secretFile) ? readFileSync(secretFile) : randomBytes(32);
if (!existsSync(secretFile)) writeFileSync(secretFile, secret, { mode: 0o600 });
const data = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : {};
const demoPatient = JSON.parse(readFileSync(new URL('../../apps/web/src/data/demoPatient.json', import.meta.url), 'utf8'));
for (const key of ['accounts', 'assignments', 'food', 'bolus', 'glucose', 'messages', 'ratings']) data[key] ||= [];
const save = () => writeFileSync(file, JSON.stringify(data, null, 2));
const passwordHash = (password, salt = randomBytes(16).toString('hex')) => `${salt}:${scryptSync(password, salt, 64).toString('hex')}`;
if (!data.accounts.length) {
  for (const [id, name, email, specialty, yearsExperience, medicalSchool, bio] of [
    ['DR-001', 'Dr. Sarah Ahmed', 'sarah.ahmed@clinic.example', 'Endocrinology', '12', 'Cairo University Faculty of Medicine', 'Focuses on continuous glucose monitoring and collaborative diabetes care.'],
    ['DR-002', 'Dr. Khaled Mansour', 'khaled.mansour@clinic.example', 'Diabetology', '18', 'Alexandria University Faculty of Medicine', 'Works with adults managing insulin therapy and long-term glucose patterns.'],
    ['DR-003', 'Dr. Reem Osman', 'reem.osman@clinic.example', 'Internal Medicine', '10', 'Ain Shams University Faculty of Medicine', 'Supports day-to-day diabetes management and coordinated follow-up.'],
    ['DR-004', 'Dr. Nada Yassin', 'nada.yassin@clinic.example', 'Endocrinology', '14', 'Cairo University Faculty of Medicine', 'Focuses on practical treatment plans informed by glucose trends.'],
  ]) data.accounts.push({ id, role: 'doctor', email, passwordHash: passwordHash('password'), doctorProfile: { fullName: name, specialty, yearsExperience, medicalSchool, bio } });
  data.accounts.push({ id: 'omar-hassan', role: 'patient', email: 'omar.hassan@example.com', passwordHash: passwordHash('password'), patientProfile: { fullName: 'Omar Hassan', age: '34', weight: '82', height: '178', diabetesType: 'Type 1 Diabetes', insulinPlan: 'Basal-bolus therapy', diagnosisYear: '2012', medications: 'Insulin', allergies: 'None reported', emergencyContact: '', selectedDoctorId: 'DR-001' } });
  data.assignments.push({ patientId: 'omar-hassan', doctorId: 'DR-001', status: 'accepted' });
  save();
}
const seededDoctorDetails = {
  'DR-001': { medicalSchool: 'Cairo University Faculty of Medicine', bio: 'Focuses on continuous glucose monitoring and collaborative diabetes care.' },
  'DR-002': { medicalSchool: 'Alexandria University Faculty of Medicine', bio: 'Works with adults managing insulin therapy and long-term glucose patterns.' },
  'DR-003': { medicalSchool: 'Ain Shams University Faculty of Medicine', bio: 'Supports day-to-day diabetes management and coordinated follow-up.' },
  'DR-004': { medicalSchool: 'Cairo University Faculty of Medicine', bio: 'Focuses on practical treatment plans informed by glucose trends.' },
};
let seededProfilesUpdated = false;
for (const account of data.accounts) {
  const details = seededDoctorDetails[account.id];
  if (!details || (account.doctorProfile?.medicalSchool && account.doctorProfile?.bio)) continue;
  account.doctorProfile = { ...details, ...account.doctorProfile };
  seededProfilesUpdated = true;
}
if (seededProfilesUpdated) save();
if (!data.ratings.length) {
  data.ratings = [
    ['DR-001', 5], ['DR-001', 5], ['DR-001', 4],
    ['DR-002', 5], ['DR-002', 4], ['DR-002', 4],
    ['DR-003', 5], ['DR-003', 4],
    ['DR-004', 5], ['DR-004', 5], ['DR-004', 5],
  ].map(([doctorId, score], index) => ({ id: `r${index + 1}`, doctorId, patientId: `demo-${index + 1}`, score, source: 'demo' }));
  save();
}
let demoRecordsAdded = false;
for (const kind of ['food', 'bolus', 'glucose', 'messages']) for (const entry of demoPatient[kind]) {
  if (!data[kind].some((item) => item.id === entry.id)) { data[kind].push(entry); demoRecordsAdded = true; }
}
if (demoRecordsAdded) save();
const validPassword = (password, stored) => {
  const [salt, digest] = stored.split(':');
  return timingSafeEqual(scryptSync(password, salt, 64), Buffer.from(digest, 'hex'));
};
const makeToken = (account) => {
  const payload = Buffer.from(JSON.stringify({ id: account.id, role: account.role, exp: Date.now() + 7 * 86400000 })).toString('base64url');
  return `${payload}.${createHmac('sha256', secret).update(payload).digest('base64url')}`;
};
const auth = (req) => {
  const [payload, signature] = (req.headers.authorization || '').replace(/^Bearer /, '').split('.');
  if (!payload || !signature) return null;
  const expected = createHmac('sha256', secret).update(payload).digest('base64url');
  if (signature.length !== expected.length || !timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  try {
    const claims = JSON.parse(Buffer.from(payload, 'base64url').toString());
    return claims.exp > Date.now() ? data.accounts.find((item) => item.id === claims.id && item.role === claims.role) : null;
  } catch { return null; }
};
const reply = (res, status, payload) => {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS' });
  res.end(JSON.stringify(payload));
};
const readBody = async (req) => {
  let raw = '';
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 5 * 1024 * 1024) throw new Error('Request too large');
  }
  return JSON.parse(raw || '{}');
};
const publicAccount = ({ passwordHash: _passwordHash, ...account }) => account;
const doctorRating = (doctorId) => {
  const all = data.ratings.filter((rating) => rating.doctorId === doctorId);
  const patients = all.filter((rating) => rating.source === 'patient');
  const used = patients.length ? patients : all;
  return { average: used.length ? used.reduce((sum, rating) => sum + rating.score, 0) / used.length : null, count: used.length, sample: used.length > 0 && !patients.length };
};
const publicDoctors = () => data.accounts.filter((item) => item.role === 'doctor').map((item) => ({ ...publicAccount(item), rating: doctorRating(item.id) }));
const publicRatings = (patientId = '') => data.ratings.map((rating) => ({ ...rating, patientId: rating.patientId === patientId ? patientId : '' }));
const acceptedDoctor = (patientId) => data.assignments.find((item) => item.patientId === patientId && item.status === 'accepted')?.doctorId;
const canReadPatient = (user, patientId) => user.role === 'patient' ? user.id === patientId : user.role === 'doctor' && acceptedDoctor(patientId) === user.id;

createServer(async (req, res) => {
  if (req.method === 'OPTIONS') return reply(res, 204, {});
  try {
    const path = new URL(req.url, 'http://localhost').pathname;
    if (req.method === 'GET' && path === '/api/doctors') return reply(res, 200, { doctors: publicDoctors(), ratings: publicRatings() });
    if (req.method === 'POST' && path === '/api/auth/bridge') {
      const { account } = await readBody(req);
      if (!account || !['patient', 'doctor'].includes(account.role) || !account.id || !account.email || typeof account.password !== 'string') return reply(res, 400, { error: 'Invalid account' });
      let stored = data.accounts.find((item) => item.email.toLowerCase() === account.email.toLowerCase());
      if (!stored && account.password.length < 8) return reply(res, 400, { error: 'Password must be at least 8 characters' });
      if (stored && (stored.id !== account.id || stored.role !== account.role || !validPassword(account.password, stored.passwordHash))) return reply(res, 401, { error: 'Account mismatch' });
      if (!stored) {
        stored = { id: account.id, role: account.role, email: account.email.toLowerCase(), passwordHash: passwordHash(account.password), patientProfile: account.patientProfile, doctorProfile: account.doctorProfile };
        data.accounts.push(stored);
      } else {
        stored.patientProfile = account.patientProfile;
        stored.doctorProfile = account.doctorProfile;
      }
      if (stored.role === 'patient' && stored.patientProfile?.selectedDoctorId) {
        data.assignments = data.assignments.filter((item) => item.patientId !== stored.id || item.doctorId === stored.patientProfile.selectedDoctorId);
        if (!data.assignments.some((item) => item.patientId === stored.id)) data.assignments.push({ patientId: stored.id, doctorId: stored.patientProfile.selectedDoctorId, status: 'pending' });
      }
      save();
      return reply(res, 200, { token: makeToken(stored), account: publicAccount(stored) });
    }
    if (req.method === 'POST' && path === '/api/auth/login') {
      const input = await readBody(req);
      const role = input.role === 'doctor' ? 'doctor' : 'patient';
      const account = data.accounts.find((item) => item.role === role && item.email.toLowerCase() === String(input.email || '').toLowerCase());
      return account && validPassword(String(input.password || ''), account.passwordHash)
        ? reply(res, 200, { token: makeToken(account), account: publicAccount(account) })
        : reply(res, 401, { error: 'Incorrect email or password' });
    }
    const user = auth(req);
    if (!user) return reply(res, 401, { error: 'Sign in required' });
    if (req.method === 'GET' && path === '/api/snapshot') {
      const patientIds = user.role === 'patient' ? [user.id] : data.assignments.filter((item) => item.doctorId === user.id).map((item) => item.patientId);
      const visibleIds = user.role === 'patient' ? patientIds : patientIds.filter((id) => acceptedDoctor(id) === user.id);
      return reply(res, 200, {
        account: publicAccount(user),
        doctors: publicDoctors(),
        ratings: publicRatings(user.role === 'patient' ? user.id : ''),
        patients: data.accounts.filter((item) => patientIds.includes(item.id)).map(publicAccount),
        assignments: data.assignments.filter((item) => user.role === 'patient' ? item.patientId === user.id : item.doctorId === user.id),
        food: data.food.filter((item) => visibleIds.includes(item.patientSlug)),
        bolus: data.bolus.filter((item) => visibleIds.includes(item.patientSlug)),
        glucose: data.glucose.filter((item) => visibleIds.includes(item.patientSlug)),
        demo: user.role === 'patient' && user.id === demoPatient.patientId ? { summary: demoPatient.summary, cgm: demoPatient.cgm, forecast: demoPatient.forecast, forecastSnapshots: demoPatient.forecastSnapshots } : null,
        messages: data.messages.filter((item) => visibleIds.includes(item.patientSlug) && (user.role === 'patient' ? item.doctorId === user.patientProfile?.selectedDoctorId : item.doctorId === user.id)),
      });
    }
    if (req.method === 'POST' && path === '/api/assignment') {
      if (user.role !== 'doctor') return reply(res, 403, { error: 'Doctor access required' });
      const input = await readBody(req);
      const assignment = data.assignments.find((item) => item.doctorId === user.id && item.patientId === input.patientId);
      if (!assignment || !['accepted', 'declined'].includes(input.status)) return reply(res, 400, { error: 'Invalid assignment' });
      assignment.status = input.status;
      save();
      return reply(res, 200, { assignment });
    }
    if (req.method === 'POST' && path === '/api/patient/doctor-request') {
      if (user.role !== 'patient') return reply(res, 403, { error: 'Patient access required' });
      const input = await readBody(req);
      const doctor = data.accounts.find((item) => item.id === input.doctorId && item.role === 'doctor');
      if (!doctor) return reply(res, 400, { error: 'Choose an available doctor' });
      const current = data.assignments.find((item) => item.patientId === user.id && item.doctorId === doctor.id);
      if (user.patientProfile?.selectedDoctorId === doctor.id && current?.status !== 'declined') return reply(res, 200, { assignment: current });
      data.assignments = data.assignments.filter((item) => item.patientId !== user.id);
      user.patientProfile = { ...user.patientProfile, selectedDoctorId: doctor.id };
      const assignment = { patientId: user.id, doctorId: doctor.id, status: 'pending' };
      data.assignments.push(assignment);
      save();
      return reply(res, 200, { assignment });
    }
    if (req.method === 'POST' && path === '/api/rating') {
      if (user.role !== 'patient') return reply(res, 403, { error: 'Patient access required' });
      const input = await readBody(req);
      if (input.doctorId !== user.patientProfile?.selectedDoctorId || !data.accounts.some((item) => item.id === input.doctorId && item.role === 'doctor') || !Number.isInteger(input.score) || input.score < 1 || input.score > 5) return reply(res, 400, { error: 'Invalid rating' });
      data.ratings = data.ratings.filter((item) => !(item.patientId === user.id && item.doctorId === input.doctorId && item.source === 'patient'));
      data.ratings.push({ id: randomBytes(12).toString('hex'), doctorId: input.doctorId, patientId: user.id, score: input.score, source: 'patient' });
      save();
      return reply(res, 200, { ratings: publicRatings(user.id) });
    }
    const match = path.match(/^\/api\/(food|bolus|glucose|messages)$/);
    if (req.method === 'POST' && match) {
      const kind = match[1];
      const item = await readBody(req);
      if (!item.id || !item.patientSlug || !canReadPatient(user, item.patientSlug)) return reply(res, 403, { error: 'Record is not available to this account' });
      if (kind !== 'messages' && user.role !== 'patient') return reply(res, 403, { error: 'Patient access required' });
      if (kind === 'messages' && item.from !== user.role) return reply(res, 403, { error: 'Invalid sender' });
      if (kind === 'messages' && !acceptedDoctor(item.patientSlug)) return reply(res, 403, { error: 'Messaging opens after doctor acceptance' });
      if (!data[kind].some((existing) => existing.id === item.id)) {
        data[kind].unshift({ ...item, doctorId: kind === 'messages' ? acceptedDoctor(item.patientSlug) : undefined });
        save();
      }
      return reply(res, 200, { ok: true });
    }
    return reply(res, 404, { error: 'Not found' });
  } catch (error) {
    return reply(res, 400, { error: error.message || 'Request failed' });
  }
}).listen(Number(process.env.SYNC_PORT || 8787), process.env.SYNC_HOST || '127.0.0.1', () => console.log(`Patient sync API listening on ${process.env.SYNC_HOST || '127.0.0.1'}:${process.env.SYNC_PORT || 8787}`));
