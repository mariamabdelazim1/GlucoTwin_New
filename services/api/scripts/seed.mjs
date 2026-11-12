import { readFile } from 'node:fs/promises';
import { createPool, databaseUrl, withTransaction } from '../db.mjs';
import { passwordHash, withoutLocalSyncMetadata } from '../lib.mjs';

const useTest = process.argv.includes('--test');
const pool = createPool({ connectionString: databaseUrl({ test: useTest }) });
const demo = JSON.parse(await readFile(new URL('../../../apps/web/src/data/demoPatient.json', import.meta.url), 'utf8'));
const doctors = [
  ['DR-001', 'Dr. Sarah Ahmed', 'sarah.ahmed@clinic.example', 'Endocrinology', '12', 'Cairo University Faculty of Medicine', 'Focuses on continuous glucose monitoring and collaborative diabetes care.'],
  ['DR-002', 'Dr. Khaled Mansour', 'khaled.mansour@clinic.example', 'Diabetology', '18', 'Alexandria University Faculty of Medicine', 'Works with adults managing insulin therapy and long-term glucose patterns.'],
  ['DR-003', 'Dr. Reem Osman', 'reem.osman@clinic.example', 'Internal Medicine', '10', 'Ain Shams University Faculty of Medicine', 'Supports day-to-day diabetes management and coordinated follow-up.'],
  ['DR-004', 'Dr. Nada Yassin', 'nada.yassin@clinic.example', 'Endocrinology', '14', 'Cairo University Faculty of Medicine', 'Focuses on practical treatment plans informed by glucose trends.'],
];

const grams = (value) => Number(String(value).match(/^(\d+(?:\.\d+)?)g$/i)?.[1]);
const units = (value) => Number(String(value).match(/^(\d+(?:\.\d+)?)\s*U$/i)?.[1]);
const at = (time) => `2026-01-01T${time}:00Z`;

try {
  await withTransaction(pool, async (db) => {
    for (const [id, fullName, email, specialty, yearsExperience, medicalSchool, bio] of doctors) {
      await db.query(`INSERT INTO users(id,role,email,password_hash) VALUES($1,'doctor',$2,$3) ON CONFLICT DO NOTHING`, [id, email, passwordHash('password')]);
      await db.query(`INSERT INTO doctor_profiles(user_id,full_name,specialty,years_experience,medical_school,bio)
        VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING`, [id, fullName, specialty, Number(yearsExperience), medicalSchool, bio]);
    }
    await db.query(`INSERT INTO users(id,role,email,password_hash) VALUES('omar-hassan','patient','omar.hassan@example.com',$1) ON CONFLICT DO NOTHING`, [passwordHash('password')]);
    await db.query(`INSERT INTO patient_profiles(user_id,full_name,age_years,weight_kg,height_cm,diabetes_type,insulin_plan,diagnosis_year,medications,allergies,legacy_emergency_contact,selected_doctor_id)
      VALUES('omar-hassan','Omar Hassan',34,82,178,'Type 1 Diabetes','Basal-bolus therapy',2012,'Insulin','None reported',NULL,'DR-001')
      ON CONFLICT DO NOTHING`);
    await db.query(`INSERT INTO care_assignments(id,patient_id,doctor_id,status,responded_at)
      VALUES('demo-assignment','omar-hassan','DR-001','accepted',now()) ON CONFLICT DO NOTHING`);
    await db.query(`INSERT INTO conversations(id,patient_id,doctor_id,assignment_id,status)
      VALUES('demo-conversation','omar-hassan','DR-001','demo-assignment','active') ON CONFLICT DO NOTHING`);
    for (const [doctorId, score, index] of [
      ['DR-001',5,1],['DR-001',5,2],['DR-001',4,3],['DR-002',5,4],['DR-002',4,5],
      ['DR-002',4,6],['DR-003',5,7],['DR-003',4,8],['DR-004',5,9],['DR-004',5,10],['DR-004',5,11],
    ]) await db.query(`INSERT INTO doctor_ratings(id,doctor_id,patient_id,score,source)
      VALUES($1,$2,NULL,$3,'demo') ON CONFLICT DO NOTHING`, [`demo-rating-${index}`, doctorId, score]);
    for (const item of demo.glucose) await db.query(`INSERT INTO glucose_readings
      (id,patient_id,measured_at,glucose_mg_dl,source,legacy_payload) VALUES($1,$2,$3,$4,'demo',$5) ON CONFLICT DO NOTHING`,
      [item.id, item.patientSlug, item.recordedAt, item.value, JSON.stringify(withoutLocalSyncMetadata(item))]);
    for (const item of demo.food) await db.query(`INSERT INTO meals
      (id,patient_id,meal_name,description,announced_carbs_g,planned_eating_at,status,actual_eating_at,consumed_carbs_g,decision_source,confirmation_provenance,legacy_payload)
      VALUES($1,$2,$3,$4,$5,$6,'eaten',$6,$5,'user_chosen',$7,$8) ON CONFLICT DO NOTHING`,
      [item.id, item.patientSlug, item.meal, item.items, grams(item.carbs), at(item.time), JSON.stringify({ source: 'documented_synthetic_fixture' }), JSON.stringify(withoutLocalSyncMetadata(item))]);
    for (const item of demo.bolus) await db.query(`INSERT INTO insulin_doses
      (id,patient_id,administered_units,carbs_g,administered_at,decision_source,confirmation_provenance,legacy_payload)
      VALUES($1,$2,$3,$4,$5,'user_decided',$6,$7) ON CONFLICT DO NOTHING`,
      [item.id, item.patientSlug, units(item.recorded), grams(item.carbs), at(item.time), JSON.stringify({ synthetic: true }), JSON.stringify(withoutLocalSyncMetadata(item))]);
    for (const item of demo.messages) await db.query(`INSERT INTO messages
      (id,conversation_id,sender_id,body,sent_at,is_read,legacy_payload) VALUES($1,'demo-conversation',$2,$3,$4,$5,$6)
      ON CONFLICT DO NOTHING`, [item.id, item.from === 'patient' ? item.patientSlug : item.doctorId, item.text, at(item.time), !item.unread, JSON.stringify(withoutLocalSyncMetadata(item))]);
  });
  console.log(`Seeded ${useTest ? 'test' : 'development'} demo data (idempotent)`);
} finally {
  await pool.end();
}

