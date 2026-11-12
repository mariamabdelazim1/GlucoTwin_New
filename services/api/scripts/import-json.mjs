import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createPool, databaseUrl, withTransaction } from '../db.mjs';
import { optionalNumber, strictUnit, timestamp, withoutLocalSyncMetadata } from '../lib.mjs';
import { accountById, publicAccount, updateProfile } from '../store.mjs';

const sourcePath = process.argv.find((value, index) => index > 1 && !value.startsWith('--'));
if (!sourcePath) throw new Error('Usage: npm run db:import -- /absolute/path/to/data.json');
const source = JSON.parse(await readFile(resolve(sourcePath), 'utf8'));
const issues = [];
const arrays = ['accounts', 'assignments', 'food', 'bolus', 'glucose', 'messages', 'ratings'];
for (const name of arrays) if (!Array.isArray(source[name])) issues.push(`${name}: expected an array`);

const demoIds = new Set(['f1','f2','f3','f4','b1','b2','b3','demo-message-patient','demo-message-doctor']);
const eventTime = (item, field, collection) => {
  const value = item[field];
  if (value) {
    try { return timestamp(value, `${collection} ${field}`); }
    catch (error) { issues.push(`${collection}/${item.id || '?'}: ${error.message}`); return null; }
  }
  if (demoIds.has(item.id) && /^\d\d:\d\d$/.test(item.time || '')) return `2026-01-01T${item.time}:00Z`;
  issues.push(`${collection}/${item.id || '?'}: missing unambiguous timezone-aware event timestamp`);
  return null;
};
const parsed = { food: [], bolus: [], glucose: [], messages: [] };
for (const item of source.glucose || []) {
  const when = eventTime(item, 'recordedAt', 'glucose');
  let value = null;
  try { value = optionalNumber(item.value, 'Glucose'); } catch (error) { issues.push(`glucose/${item.id || '?'}: ${error.message}`); }
  if (value === null) issues.push(`glucose/${item.id || '?'}: missing value`);
  parsed.glucose.push({ item, when, value });
}
for (const item of source.food || []) {
  let carbs = null;
  try { carbs = item.carbs !== undefined ? strictUnit(item.carbs, 'g', 'carbohydrates') : optionalNumber(item.announcedCarbsG, 'carbohydrates'); }
  catch (error) { issues.push(`food/${item.id || '?'}: ${error.message}`); }
  if (carbs === null) issues.push(`food/${item.id || '?'}: missing carbohydrates`);
  const synthetic = demoIds.has(item.id);
  const status = synthetic ? 'eaten' : ['planned', 'cancelled'].includes(item.status) ? item.status :
    item.status === 'eaten' && item.actualEatingAt && (item.consumedCarbsG !== undefined || item.confirmAnnouncedAmount === true) ? 'eaten' : 'planned';
  const plannedAt = eventTime(item, 'plannedEatingAt', 'food');
  const actualAt = status === 'eaten' ? (synthetic ? plannedAt : eventTime(item, 'actualEatingAt', 'food')) : null;
  let consumed = null;
  if (status === 'eaten') {
    try { consumed = synthetic || item.confirmAnnouncedAmount === true ? carbs : optionalNumber(item.consumedCarbsG, 'consumed carbohydrates'); }
    catch (error) { issues.push(`food/${item.id || '?'}: ${error.message}`); }
    if (consumed === null) issues.push(`food/${item.id || '?'}: eaten meal is missing confirmed consumption`);
  }
  parsed.food.push({ item, plannedAt, actualAt, carbs, consumed, status, synthetic });
}
for (const item of source.bolus || []) {
  let amount = null;
  try { amount = strictUnit(item.recorded, 'U', 'administered insulin'); } catch (error) { issues.push(`bolus/${item.id || '?'}: ${error.message}`); }
  let carbs = null;
  try {
    carbs = Object.hasOwn(item, 'carbsG') ? optionalNumber(item.carbsG, 'carbohydrates')
      : Object.hasOwn(item, 'carbs') ? strictUnit(item.carbs, 'g', 'carbohydrates') : null;
  } catch (error) { issues.push(`bolus/${item.id || '?'}: ${error.message}`); }
  parsed.bolus.push({ item, when: eventTime(item, 'administeredAt', 'bolus'), amount, carbs });
}
for (const item of source.messages || []) parsed.messages.push({ item, when: eventTime(item, 'sentAt', 'messages') });
if (issues.length) {
  console.error('Import validation failed; database was not changed:');
  for (const issue of issues) console.error(`- ${issue}`);
  process.exitCode = 1;
} else {
  const pool = createPool({ connectionString: databaseUrl() });
  try {
    await withTransaction(pool, async (db) => {
      const insertedAccounts = new Set();
      for (const account of source.accounts) {
        if (!account.id || !['patient','doctor'].includes(account.role) || !account.email || !account.passwordHash) throw new Error(`Invalid account ${account.id || '?'}`);
        const existing = (await db.query('SELECT role,email,password_hash FROM users WHERE id=$1', [account.id])).rows[0];
        if (existing) {
          if (existing.role !== account.role || existing.email.toLowerCase() !== account.email.toLowerCase() || existing.password_hash !== account.passwordHash) throw new Error(`Account ${account.id} conflicts with existing database content`);
        } else {
          await db.query(`INSERT INTO users(id,role,email,password_hash) VALUES($1,$2,$3,$4)`, [account.id, account.role, account.email.toLowerCase(), account.passwordHash]);
          insertedAccounts.add(account.id);
        }
      }
      for (const account of source.accounts) {
        if (insertedAccounts.has(account.id)) {
          await updateProfile(db, account.id, account.role, account.patientProfile || account.doctorProfile || {});
          continue;
        }
        const current = publicAccount(await accountById(db, account.id));
        const incomingProfile = account.patientProfile || account.doctorProfile || {};
        const currentProfile = account.role === 'patient' ? current.patientProfile : current.doctorProfile;
        for (const [key, value] of Object.entries(incomingProfile)) {
          if (JSON.stringify(currentProfile?.[key] ?? '') !== JSON.stringify(value ?? '')) throw new Error(`Account ${account.id} profile conflicts at ${key}`);
        }
      }
      const insertLegacy = async (table, item, insert) => {
        const compatibilityPayload = withoutLocalSyncMetadata(item);
        const existing = (await db.query(`SELECT patient_id,
          (legacy_payload - 'syncState' - 'syncAttempts' - 'syncNextAttemptAt' - 'syncError') = $2::jsonb same_payload
          FROM ${table} WHERE id=$1`, [item.id, JSON.stringify(compatibilityPayload)])).rows[0];
        if (existing) {
          if (existing.patient_id !== item.patientSlug || !existing.same_payload) throw new Error(`${table}/${item.id} conflicts with existing database content`);
          return;
        }
        await insert();
      };
      let ordinal = 0;
      for (const item of source.assignments) {
        const id = item.id || `legacy-assignment-${ordinal++}-${item.patientId}-${item.doctorId}`;
        const status = ['pending','accepted','declined','ended'].includes(item.status) ? item.status : 'pending';
        const existing = (await db.query('SELECT patient_id,doctor_id,status FROM care_assignments WHERE id=$1', [id])).rows[0];
        if (existing && (existing.patient_id !== item.patientId || existing.doctor_id !== item.doctorId || existing.status !== status)) throw new Error(`care_assignment/${id} conflicts with existing database content`);
        if (!existing) await db.query(`INSERT INTO care_assignments(id,patient_id,doctor_id,status,responded_at,ended_at)
          VALUES($1,$2,$3,$4,CASE WHEN $4 IN ('accepted','declined') THEN now() END,CASE WHEN $4='ended' THEN now() END)`, [id, item.patientId, item.doctorId, status]);
        if (status === 'accepted') await db.query(`INSERT INTO conversations(id,patient_id,doctor_id,assignment_id,status)
          VALUES($1,$2,$3,$4,'active') ON CONFLICT(assignment_id) DO NOTHING`, [`legacy-conversation-${id}`, item.patientId, item.doctorId, id]);
      }
      for (const { item, when, value } of parsed.glucose) await insertLegacy('glucose_readings', item, () => db.query(`INSERT INTO glucose_readings
        (id,patient_id,measured_at,glucose_mg_dl,source,legacy_payload) VALUES($1,$2,$3,$4,'imported',$5)`, [item.id,item.patientSlug,when,value,JSON.stringify(withoutLocalSyncMetadata(item))]));
      for (const { item, plannedAt, actualAt, carbs, consumed, status, synthetic } of parsed.food) await insertLegacy('meals', item, () => db.query(`INSERT INTO meals
        (id,patient_id,meal_name,description,announced_carbs_g,planned_eating_at,status,actual_eating_at,consumed_carbs_g,decision_source,confirmation_provenance,legacy_payload)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'user_chosen',$10,$11)`, [item.id,item.patientSlug,item.meal,item.items,carbs,plannedAt,status,actualAt,consumed,
        JSON.stringify(status === 'eaten' ? { source: synthetic ? 'documented_synthetic_fixture' : item.confirmAnnouncedAmount === true ? 'imported_patient_confirmation' : 'imported_explicit_actual' } : { source: 'ambiguous_legacy_import_requires_review' }),JSON.stringify(withoutLocalSyncMetadata(item))]));
      for (const { item, when, amount, carbs } of parsed.bolus) await insertLegacy('insulin_doses', item, () => db.query(`INSERT INTO insulin_doses
        (id,patient_id,administered_units,carbs_g,administered_at,decision_source,confirmation_provenance,legacy_payload)
        VALUES($1,$2,$3,$4,$5,'user_decided',$6,$7)`, [item.id,item.patientSlug,amount,carbs,when,JSON.stringify({ source: 'legacy_import' }),JSON.stringify(withoutLocalSyncMetadata(item))]));
      for (const item of source.ratings) {
        const existing = (await db.query('SELECT doctor_id,patient_id,score,source FROM doctor_ratings WHERE id=$1', [item.id])).rows[0];
        const patientId = item.source==='patient'?item.patientId:null;
        const sourceType = item.source==='patient'?'patient':'imported';
        if (existing && (existing.doctor_id !== item.doctorId || existing.patient_id !== patientId || existing.score !== item.score || existing.source !== sourceType)) throw new Error(`doctor_rating/${item.id} conflicts with existing database content`);
        if (!existing) await db.query(`INSERT INTO doctor_ratings(id,doctor_id,patient_id,score,source)
          VALUES($1,$2,$3,$4,$5)`, [item.id,item.doctorId,patientId,item.score,sourceType]);
      }
      for (const { item, when } of parsed.messages) {
        const assignment = (await db.query(`SELECT * FROM care_assignments WHERE patient_id=$1 AND doctor_id=$2 AND status='accepted' ORDER BY requested_at DESC LIMIT 1`, [item.patientSlug,item.doctorId])).rows[0];
        if (!assignment) throw new Error(`Message ${item.id} has no accepted assignment`);
        const conversation = (await db.query('SELECT id FROM conversations WHERE assignment_id=$1', [assignment.id])).rows[0];
        const compatibilityPayload = withoutLocalSyncMetadata(item);
        const existing = (await db.query(`SELECT conversation_id,
          (legacy_payload - 'syncState' - 'syncAttempts' - 'syncNextAttemptAt' - 'syncError') = $2::jsonb same_payload
          FROM messages WHERE id=$1`, [item.id, JSON.stringify(compatibilityPayload)])).rows[0];
        if (existing && (existing.conversation_id !== conversation.id || !existing.same_payload)) throw new Error(`message/${item.id} conflicts with existing database content`);
        if (!existing) await db.query(`INSERT INTO messages(id,conversation_id,sender_id,body,sent_at,is_read,legacy_payload)
          VALUES($1,$2,$3,$4,$5,$6,$7)`, [item.id,conversation.id,item.from==='patient'?item.patientSlug:item.doctorId,item.text,when,!item.unread,JSON.stringify(compatibilityPayload)]);
      }
    });
    console.log(`Imported legacy data atomically from ${resolve(sourcePath)}`);
  } finally { await pool.end(); }
}
