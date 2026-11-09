import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import pg from 'pg';

const connectionString = process.env.TEST_DATABASE_URL;
if (!connectionString || !new URL(connectionString).pathname.includes('_test')) {
  throw new Error('TEST_DATABASE_URL must point to a dedicated database whose name contains _test');
}
const migration = async (name) => readFile(new URL(`../migrations/${name}`, import.meta.url), 'utf8');

async function inSchema(label, callback) {
  const client = new pg.Client({ connectionString });
  const schema = `gt_${label}_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
  await client.connect();
  try {
    await client.query(`CREATE SCHEMA "${schema}"`);
    await client.query(`SET search_path TO "${schema}", public`);
    await callback(client);
  } finally {
    await client.query('SET search_path TO public');
    await client.query(`DROP SCHEMA "${schema}" CASCADE`);
    await client.end();
  }
}

async function exerciseTriggers(db) {
  await db.query(`INSERT INTO users(id,role,email,password_hash) VALUES
    ('p1','patient','p1@test.invalid','x'),('p2','patient','p2@test.invalid','x'),
    ('d1','doctor','d1@test.invalid','x')`);
  await db.query("INSERT INTO patient_profiles(user_id,full_name,selected_doctor_id) VALUES('p1','Patient','d1')");
  await db.query("INSERT INTO doctor_profiles(user_id,full_name) VALUES('d1','Doctor')");
  await db.query("INSERT INTO glucose_readings(id,patient_id,measured_at,glucose_mg_dl,source) VALUES('g1','p1',now(),100,'manual')");
  await db.query("UPDATE glucose_readings SET glucose_mg_dl=101 WHERE id='g1'");
  await db.query("INSERT INTO predictions(id,patient_id,requested_by_user_id,forecast_origin_at,input_snapshot,input_snapshot_sha256,status) VALUES('pred','p1','p1',now(),'{}','hash','completed')");
  await db.query("INSERT INTO recommendations(id,patient_id,prediction_id,recommendation_type) VALUES('rec','p1','pred','bolus')");
  await db.query("INSERT INTO recommendation_responses(id,recommendation_id,patient_id,response) VALUES('resp','rec','p1','accepted')");
  await db.query("INSERT INTO insulin_doses(id,patient_id,administered_units,administered_at,decision_source,recommendation_id) VALUES('dose','p1',1,now(),'ai_followed','rec')");
  await db.query("INSERT INTO meals(id,patient_id,announced_carbs_g,planned_eating_at,status,decision_source,recommendation_id) VALUES('meal','p1',30,now(),'planned','ai_followed','rec')");
  await db.query("INSERT INTO care_assignments(id,patient_id,doctor_id,status) VALUES('assignment','p1','d1','accepted')");
  await db.query("INSERT INTO conversations(id,patient_id,doctor_id,assignment_id,status) VALUES('conversation','p1','d1','assignment','active')");
  await db.query("INSERT INTO messages(id,conversation_id,sender_id,body) VALUES('message','conversation','p1','hello')");
  await db.query("UPDATE patient_profiles SET full_name='Patient Updated' WHERE user_id='p1'");
  await db.query("UPDATE meals SET description='updated' WHERE id='meal'");
  await db.query("UPDATE insulin_doses SET administered_units=1.5 WHERE id='dose'");
  await db.query("UPDATE recommendations SET suggested_amount=2 WHERE id='rec'");
  await db.query("UPDATE recommendation_responses SET response='modified' WHERE id='resp'");
  await db.query("UPDATE care_assignments SET responded_at=now() WHERE id='assignment'");
  await assert.rejects(db.query("INSERT INTO glucose_readings(id,patient_id,measured_at,glucose_mg_dl,source) VALUES('bad-role','d1',now(),100,'manual')"));
  await assert.rejects(db.query("INSERT INTO patient_profiles(user_id,full_name) VALUES('d1','Not Patient')"));
  await assert.rejects(db.query("INSERT INTO care_assignments(id,patient_id,doctor_id,status) VALUES('bad-doctor','p1','p2','pending')"));
  await assert.rejects(db.query("INSERT INTO recommendations(id,patient_id,prediction_id,recommendation_type) VALUES('bad-link','p2','pred','bolus')"));
  await assert.rejects(db.query("UPDATE insulin_doses SET patient_id='p2' WHERE id='dose'"));
  await assert.rejects(db.query("INSERT INTO messages(id,conversation_id,sender_id,body) VALUES('bad-sender','conversation','p2','no')"));
  await assert.rejects(db.query("INSERT INTO meals(id,patient_id,announced_carbs_g,planned_eating_at,status,decision_source) VALUES('bad-life','p1',10,now(),'eaten','user_chosen')"));
  await assert.rejects(db.query("INSERT INTO glucose_readings(id,patient_id,measured_at,glucose_mg_dl,source) VALUES('bad-nan','p1',now(),'NaN','manual')"));
}

test('fresh database applies all migrations and trigger invariants permit real writes', async () => {
  await inSchema('fresh', async (db) => {
    await db.query(await migration('001_initial.sql'));
    await db.query(await migration('002_repair_triggers_and_meals.sql'));
    await exerciseTriggers(db);
  });
});

test('database with 001 upgrades through the forward repair migration', async () => {
  await inSchema('upgrade', async (db) => {
    await db.query(await migration('001_initial.sql'));
    await db.query(await migration('002_repair_triggers_and_meals.sql'));
    await exerciseTriggers(db);
  });
});
