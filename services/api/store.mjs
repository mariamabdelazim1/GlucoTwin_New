import { ApiError, contentHash, finiteNonnegative, newId, optionalNumber, strictUnit, timestamp, withoutLocalSyncMetadata } from './lib.mjs';
import { withTransaction } from './db.mjs';

const text = (value) => value === undefined || value === null ? '' : String(value);
const legacyPayload = (row) => withoutLocalSyncMetadata(row.legacy_payload);

function accountFromRow(row) {
  if (!row) return null;
  const account = { id: row.id, role: row.role, email: row.email };
  if (row.role === 'patient') account.patientProfile = {
    fullName: row.patient_full_name || '', age: text(row.age_years), weight: text(row.weight_kg),
    height: text(row.height_cm), diabetesType: row.diabetes_type || '', insulinPlan: row.insulin_plan || '',
    diagnosisYear: text(row.diagnosis_year), medications: row.medications || '', allergies: row.allergies || '',
    emergencyContact: row.legacy_emergency_contact || '', selectedDoctorId: row.selected_doctor_id || '',
  };
  if (row.role === 'doctor') account.doctorProfile = {
    fullName: row.doctor_full_name || '', specialty: row.specialty || '', yearsExperience: text(row.years_experience),
    medicalSchool: row.medical_school || '', qualifications: row.qualifications || '', bio: row.bio || '',
    certificates: row.certificates || [], papers: row.papers || [], photo: row.photo || undefined,
    documents: row.documents || [],
  };
  return account;
}

const accountSelect = `
  SELECT u.id, u.role, u.email, u.password_hash,
    pp.full_name patient_full_name, pp.age_years, pp.weight_kg, pp.height_cm,
    pp.diabetes_type, pp.insulin_plan, pp.diagnosis_year, pp.medications, pp.allergies,
    pp.selected_doctor_id, pp.legacy_emergency_contact,
    dp.full_name doctor_full_name, dp.specialty, dp.years_experience, dp.medical_school,
    dp.qualifications, dp.bio, dp.certificates, dp.papers, dp.photo, dp.documents
  FROM users u
  LEFT JOIN patient_profiles pp ON pp.user_id = u.id
  LEFT JOIN doctor_profiles dp ON dp.user_id = u.id`;

export async function accountById(db, id) {
  return (await db.query(`${accountSelect} WHERE u.id = $1`, [id])).rows[0] || null;
}

export async function accountByEmail(db, email, role) {
  const params = [String(email).toLowerCase()];
  let condition = 'lower(u.email) = $1';
  if (role) { params.push(role); condition += ' AND u.role = $2'; }
  return (await db.query(`${accountSelect} WHERE ${condition}`, params)).rows[0] || null;
}

export const publicAccount = accountFromRow;

export const mealJson = (row) => {
  const legacy = legacyPayload(row);
  return {
    ...legacy,
    id: row.id,
    patientSlug: row.patient_id,
    meal: row.meal_name || legacy.meal || '',
    items: row.description || legacy.items || '',
    carbs: row.announced_carbs_g === null ? '' : `${Number(row.announced_carbs_g)}g`,
    announcedCarbsG: row.announced_carbs_g === null ? null : Number(row.announced_carbs_g),
    consumedCarbsG: row.consumed_carbs_g === null ? null : Number(row.consumed_carbs_g),
    plannedEatingAt: row.planned_eating_at.toISOString(),
    actualEatingAt: row.actual_eating_at?.toISOString() || null,
    status: row.status,
    version: row.version,
    updatedAt: row.updated_at.toISOString(),
    confirmationProvenance: row.confirmation_provenance || {},
    time: legacy.time || row.planned_eating_at.toISOString(),
  };
};

function optionalProfileNumber(profile, field, label) {
  const value = profile[field];
  if (typeof value === 'string' && value.trim() === '') return null;
  return optionalNumber(value, label);
}

export async function updateProfile(db, userId, role, profile = {}) {
  if (role === 'patient') {
    await db.query(`INSERT INTO patient_profiles(
      user_id, full_name, age_years, weight_kg, height_cm, diabetes_type, insulin_plan,
      diagnosis_year, medications, allergies, legacy_emergency_contact, selected_doctor_id
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
    ON CONFLICT (user_id) DO UPDATE SET
      full_name=EXCLUDED.full_name,
      age_years=CASE WHEN $13 THEN EXCLUDED.age_years ELSE patient_profiles.age_years END,
      weight_kg=CASE WHEN $14 THEN EXCLUDED.weight_kg ELSE patient_profiles.weight_kg END,
      height_cm=CASE WHEN $15 THEN EXCLUDED.height_cm ELSE patient_profiles.height_cm END,
      diabetes_type=EXCLUDED.diabetes_type,
      insulin_plan=EXCLUDED.insulin_plan,
      diagnosis_year=CASE WHEN $16 THEN EXCLUDED.diagnosis_year ELSE patient_profiles.diagnosis_year END,
      medications=EXCLUDED.medications, allergies=EXCLUDED.allergies,
      legacy_emergency_contact=EXCLUDED.legacy_emergency_contact,
      selected_doctor_id=COALESCE(EXCLUDED.selected_doctor_id, patient_profiles.selected_doctor_id)`, [
      userId, profile.fullName || 'Patient', optionalProfileNumber(profile, 'age', 'Age'), optionalProfileNumber(profile, 'weight', 'Weight'),
      optionalProfileNumber(profile, 'height', 'Height'), profile.diabetesType || null, profile.insulinPlan || null,
      optionalProfileNumber(profile, 'diagnosisYear', 'Diagnosis year'), profile.medications || null, profile.allergies || null,
      profile.emergencyContact || null, profile.selectedDoctorId || null,
      Object.hasOwn(profile, 'age'), Object.hasOwn(profile, 'weight'), Object.hasOwn(profile, 'height'),
      Object.hasOwn(profile, 'diagnosisYear'),
    ]);
  } else {
    await db.query(`INSERT INTO doctor_profiles(
      user_id, full_name, specialty, years_experience, medical_school, qualifications,
      bio, certificates, papers, photo, documents
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
    ON CONFLICT (user_id) DO UPDATE SET
      full_name=EXCLUDED.full_name, specialty=EXCLUDED.specialty,
      years_experience=CASE WHEN $12 THEN EXCLUDED.years_experience ELSE doctor_profiles.years_experience END,
      medical_school=EXCLUDED.medical_school,
      qualifications=EXCLUDED.qualifications, bio=EXCLUDED.bio, certificates=EXCLUDED.certificates,
      papers=EXCLUDED.papers, photo=EXCLUDED.photo, documents=EXCLUDED.documents`, [
      userId, profile.fullName || 'Doctor', profile.specialty || null, optionalProfileNumber(profile, 'yearsExperience', 'Years of experience'),
      profile.medicalSchool || null, profile.qualifications || null, profile.bio || null,
      JSON.stringify(profile.certificates || []), JSON.stringify(profile.papers || []), profile.photo || null,
      JSON.stringify(profile.documents || []),
      Object.hasOwn(profile, 'yearsExperience'),
    ]);
  }
}

export async function currentAcceptedAssignment(db, patientId) {
  return (await db.query(`SELECT * FROM care_assignments
    WHERE patient_id=$1 AND status='accepted' ORDER BY requested_at DESC LIMIT 1`, [patientId])).rows[0] || null;
}

export async function canReadPatient(db, user, patientId) {
  if (user.role === 'patient') return user.id === patientId;
  return Boolean((await db.query(`SELECT 1 FROM care_assignments
    WHERE patient_id=$1 AND doctor_id=$2 AND status='accepted'`, [patientId, user.id])).rowCount);
}

export async function doctorDirectory(db, visiblePatientId = '') {
  const doctors = (await db.query(`${accountSelect} WHERE u.role='doctor' ORDER BY dp.full_name`)).rows.map(accountFromRow);
  const ratings = (await db.query('SELECT id, doctor_id, patient_id, score, source FROM doctor_ratings ORDER BY created_at')).rows;
  for (const doctor of doctors) {
    const all = ratings.filter((rating) => rating.doctor_id === doctor.id);
    const patient = all.filter((rating) => rating.source === 'patient');
    const used = patient.length ? patient : all;
    doctor.rating = { average: used.length ? used.reduce((sum, item) => sum + item.score, 0) / used.length : null, count: used.length, sample: used.length > 0 && !patient.length };
  }
  return {
    doctors,
    ratings: ratings.map((rating) => ({ id: rating.id, doctorId: rating.doctor_id, patientId: rating.patient_id === visiblePatientId ? visiblePatientId : '', score: rating.score, source: rating.source === 'patient' ? 'patient' : 'demo' })),
  };
}

const assignmentJson = (row) => ({
  id: row.id, patientId: row.patient_id, doctorId: row.doctor_id, status: row.status,
  requestedAt: row.requested_at?.toISOString?.() || row.requested_at,
  respondedAt: row.responded_at?.toISOString?.() || row.responded_at || null,
});

export async function snapshot(db, user) {
  const directory = await doctorDirectory(db, user.role === 'patient' ? user.id : '');
  const assignmentRows = (await db.query(`SELECT * FROM care_assignments
    WHERE ${user.role === 'patient' ? 'patient_id=$1' : 'doctor_id=$1'} AND status <> 'ended'
    ORDER BY requested_at DESC`, [user.id])).rows;
  const visiblePatientIds = user.role === 'patient'
    ? [user.id]
    : assignmentRows.filter((row) => row.status === 'accepted').map((row) => row.patient_id);
  const patientIds = user.role === 'patient' ? [user.id] : assignmentRows.map((row) => row.patient_id);
  const patients = patientIds.length
    ? (await db.query(`${accountSelect} WHERE u.id = ANY($1::text[])`, [patientIds])).rows.map(accountFromRow)
    : [];
  const queryVisible = async (sql) => visiblePatientIds.length ? (await db.query(sql, [visiblePatientIds])).rows : [];
  const glucose = (await queryVisible(`SELECT * FROM glucose_readings WHERE patient_id=ANY($1::text[]) ORDER BY measured_at DESC`)).map((row) => {
    const legacy = legacyPayload(row);
    return { ...legacy, id: row.id, patientSlug: row.patient_id,
      value: Number(row.glucose_mg_dl), recordedAt: row.measured_at.toISOString(),
      time: legacy.time || row.measured_at.toISOString() };
  });
  const food = (await queryVisible(`SELECT * FROM meals WHERE patient_id=ANY($1::text[]) ORDER BY planned_eating_at DESC`)).map(mealJson);
  const bolus = (await queryVisible(`SELECT * FROM insulin_doses WHERE patient_id=ANY($1::text[]) ORDER BY administered_at DESC`)).map((row) => {
    const legacy = legacyPayload(row);
    return { ...legacy, id: row.id, patientSlug: row.patient_id,
      administeredUnits: Number(row.administered_units), administeredAt: row.administered_at.toISOString() };
  });
  const messages = (await db.query(`SELECT m.*, c.patient_id, c.doctor_id, sender.role sender_role
    FROM messages m JOIN conversations c ON c.id=m.conversation_id JOIN users sender ON sender.id=m.sender_id
    WHERE c.status='active' AND ${user.role === 'patient' ? 'c.patient_id=$1' : 'c.doctor_id=$1'}
    ORDER BY m.sent_at, m.id`, [user.id])).rows.map((row) => {
      const legacy = legacyPayload(row);
      return { ...legacy, id: row.id, doctorId: row.doctor_id, patientSlug: row.patient_id,
        from: row.sender_role, text: row.body, unread: !row.is_read,
        sentAt: row.sent_at.toISOString(), time: legacy.time || row.sent_at.toISOString() };
    });
  return {
    account: accountFromRow(await accountById(db, user.id)), ...directory, patients,
    assignments: assignmentRows.map(assignmentJson), food, bolus, glucose, messages,
  };
}

export async function requestDoctorInTransaction(db, patientId, doctorId) {
  await db.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', [`care-request:${patientId}`]);
  const doctor = await accountById(db, doctorId);
  if (!doctor || doctor.role !== 'doctor') throw new ApiError(400, 'Choose an available doctor');
  const existing = (await db.query(`SELECT * FROM care_assignments WHERE patient_id=$1 AND doctor_id=$2
    AND status IN ('pending','accepted')`, [patientId, doctorId])).rows[0];
  if (existing) return assignmentJson(existing);
  const ended = await db.query(`UPDATE care_assignments SET status='ended', ended_at=now()
    WHERE patient_id=$1 AND status IN ('pending','accepted') RETURNING id`, [patientId]);
  if (ended.rows.length) await db.query(`UPDATE conversations SET status='ended', ended_at=now()
    WHERE assignment_id=ANY($1::text[]) AND status='active'`, [ended.rows.map((row) => row.id)]);
  const id = newId('assignment');
  const row = (await db.query(`INSERT INTO care_assignments(id,patient_id,doctor_id,status)
    VALUES($1,$2,$3,'pending') RETURNING *`, [id, patientId, doctorId])).rows[0];
  await db.query('UPDATE patient_profiles SET selected_doctor_id=$2 WHERE user_id=$1', [patientId, doctorId]);
  await audit(db, patientId, 'care_assignment.requested', 'care_assignment', id, { doctorId });
  return assignmentJson(row);
}

export async function requestDoctor(pool, patientId, doctorId) {
  return withTransaction(pool, (db) => requestDoctorInTransaction(db, patientId, doctorId));
}

export async function respondAssignment(pool, doctorId, patientId, status) {
  if (!['accepted', 'declined'].includes(status)) throw new ApiError(400, 'Invalid assignment');
  return withTransaction(pool, async (db) => {
    await db.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', [`care-decision:${doctorId}:${patientId}`]);
    const row = (await db.query(`UPDATE care_assignments SET status=$3, responded_at=now()
      WHERE patient_id=$1 AND doctor_id=$2 AND status='pending' RETURNING *`, [patientId, doctorId, status])).rows[0];
    if (!row) {
      const latest = (await db.query(`SELECT * FROM care_assignments WHERE patient_id=$1 AND doctor_id=$2
        ORDER BY requested_at DESC LIMIT 1`, [patientId, doctorId])).rows[0];
      if (latest?.status === status) return assignmentJson(latest);
      if (latest && ['accepted', 'declined'].includes(latest.status)) throw new ApiError(409, `Request was already ${latest.status}`);
      throw new ApiError(400, 'No pending request is available');
    }
    if (status === 'accepted') {
      await db.query(`INSERT INTO conversations(id,patient_id,doctor_id,assignment_id,status)
        VALUES($1,$2,$3,$4,'active') ON CONFLICT(assignment_id) DO NOTHING`, [newId('conversation'), patientId, doctorId, row.id]);
    }
    await audit(db, doctorId, `care_assignment.${status}`, 'care_assignment', row.id, { patientId });
    return assignmentJson(row);
  });
}

export async function audit(db, actor, eventType, entityType, entityId, metadata = {}) {
  await db.query(`INSERT INTO audit_events(id,actor_user_id,event_type,entity_type,entity_id,metadata)
    VALUES($1,$2,$3,$4,$5,$6)`, [newId('audit'), actor, eventType, entityType, entityId, JSON.stringify(metadata)]);
}

const sameNumber = (left, right) => left === null && right === null || left !== null && right !== null && Number(left) === Number(right);
const sameInstant = (left, right) => left === null && right === null || left && right && new Date(left).getTime() === new Date(right).getTime();

function sameOriginalMeal(row, expected) {
  try {
    const item = legacyPayload(row);
    const legacy = Object.hasOwn(item, 'carbs');
    const announced = legacy ? strictUnit(item.carbs, 'g', 'Announced carbohydrates') : optionalNumber(item.announcedCarbsG, 'Announced carbohydrates');
    const status = ['planned', 'eaten', 'cancelled'].includes(item.status) ? item.status : legacy ? 'planned' : item.status || 'planned';
    let consumed = optionalNumber(item.consumedCarbsG, 'Consumed carbohydrates');
    if (item.confirmAnnouncedAmount === true) consumed = announced;
    if (status !== 'eaten') consumed = null;
    return (item.meal || null) === expected.mealName && (item.items || item.description || null) === expected.description
      && sameNumber(announced, expected.announced) && sameInstant(item.plannedEatingAt, expected.plannedAt)
      && status === expected.status && sameInstant(status === 'eaten' ? item.actualEatingAt : null, expected.actualAt)
      && sameNumber(consumed, expected.consumed) && (item.decisionSource || 'user_chosen') === expected.decisionSource
      && (item.recommendationId || null) === expected.recommendationId;
  } catch { return false; }
}

function sameClinicalRecord(table, row, expected) {
  if (table === 'glucose_readings') return sameNumber(row.glucose_mg_dl, expected.value)
    && sameInstant(row.measured_at, expected.measuredAt) && row.source === expected.source;
  if (table === 'insulin_doses') return sameNumber(row.administered_units, expected.units)
    && sameInstant(row.administered_at, expected.administeredAt) && row.decision_source === expected.decisionSource
    && row.recommendation_id === expected.recommendationId;
  if (table === 'meals') return row.meal_name === expected.mealName
    && row.description === expected.description && sameNumber(row.announced_carbs_g, expected.announced)
    && sameInstant(row.planned_eating_at, expected.plannedAt) && row.status === expected.status
    && sameInstant(row.actual_eating_at, expected.actualAt) && sameNumber(row.consumed_carbs_g, expected.consumed)
    && row.decision_source === expected.decisionSource && row.recommendation_id === expected.recommendationId
    || row.version > 1 && sameOriginalMeal(row, expected);
  return false;
}

async function idempotentInsert(db, table, id, patientId, expected, insert) {
  await db.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', [`${table}:${id}`]);
  const existing = (await db.query(`SELECT * FROM ${table} WHERE id=$1`, [id])).rows[0];
  if (existing) {
    if (existing.patient_id === patientId && sameClinicalRecord(table, existing, expected)) return false;
    throw new ApiError(409, 'Existing ID conflicts with different ownership or content');
  }
  await insert();
  return true;
}

export async function addPatientRecord(pool, kind, item, user) {
  if (!item?.id || !item?.patientSlug) throw new ApiError(400, 'Record ID and patient are required');
  if (user.role !== 'patient' || user.id !== item.patientSlug) throw new ApiError(403, 'Record is not available to this account');
  return withTransaction(pool, async (db) => {
    let created = false;
    if (kind === 'glucose') {
      const value = optionalNumber(item.value ?? item.glucoseMgDl, 'Glucose');
      if (value === null) throw new ApiError(400, 'Glucose must be a finite nonnegative number');
      const measuredAt = timestamp(item.recordedAt ?? item.measuredAt, 'Glucose recordedAt');
      created = await idempotentInsert(db, 'glucose_readings', item.id, user.id,
        { value, measuredAt, source: item.source || 'manual' }, () => db.query(`INSERT INTO glucose_readings
        (id,patient_id,measured_at,glucose_mg_dl,source,legacy_payload) VALUES($1,$2,$3,$4,$5,$6)`,
        [item.id, user.id, measuredAt, value, item.source || 'manual', JSON.stringify(withoutLocalSyncMetadata(item))]));
    } else if (kind === 'bolus') {
      const units = strictUnit(item.administeredUnits ?? item.recorded, 'U', 'Administered insulin');
      const administeredAt = timestamp(item.administeredAt, 'Insulin administeredAt');
      const decisionSource = item.decisionSource || 'user_decided';
      const recommendationId = item.recommendationId || null;
      created = await idempotentInsert(db, 'insulin_doses', item.id, user.id,
        { units, administeredAt, decisionSource, recommendationId }, () => db.query(`INSERT INTO insulin_doses
        (id,patient_id,administered_units,administered_at,decision_source,recommendation_id,confirmation_provenance,legacy_payload)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8)`, [item.id, user.id, units, administeredAt,
        decisionSource, recommendationId,
        JSON.stringify(item.confirmationProvenance || { source: 'patient_log' }), JSON.stringify(withoutLocalSyncMetadata(item))]));
    } else if (kind === 'food') {
      const legacy = Object.hasOwn(item, 'carbs');
      const announced = legacy ? strictUnit(item.carbs, 'g', 'Announced carbohydrates') : optionalNumber(item.announcedCarbsG, 'Announced carbohydrates');
      if (announced === null) throw new ApiError(400, 'Announced carbohydrates are required');
      const status = ['planned', 'eaten', 'cancelled'].includes(item.status)
        ? item.status : legacy && (!item.status || !['planned', 'eaten', 'cancelled'].includes(item.status)) ? 'planned' : item.status || 'planned';
      if (!['planned', 'eaten', 'cancelled'].includes(status)) throw new ApiError(400, 'Meal status must be planned, eaten, or cancelled');
      const plannedAt = timestamp(item.plannedEatingAt, 'Meal plannedEatingAt');
      const actualAt = status === 'eaten' ? timestamp(item.actualEatingAt, 'Meal actualEatingAt') : null;
      let consumed = optionalNumber(item.consumedCarbsG, 'Consumed carbohydrates');
      if (item.confirmAnnouncedAmount === true) consumed = announced;
      if (status === 'eaten' && consumed === null) throw new ApiError(400, 'An eaten meal requires consumedCarbsG or confirmAnnouncedAmount=true');
      if (status !== 'eaten' && (item.consumedCarbsG != null || item.actualEatingAt != null || item.confirmAnnouncedAmount === true)) {
        throw new ApiError(400, 'Planned and cancelled meals cannot contain confirmed consumption or an actual eating time');
      }
      if (status !== 'eaten') consumed = null;
      const mealName = item.meal || null;
      const description = item.items || item.description || null;
      const decisionSource = item.decisionSource || 'user_chosen';
      const recommendationId = item.recommendationId || null;
      created = await idempotentInsert(db, 'meals', item.id, user.id,
        { mealName, description, announced, plannedAt, status, actualAt, consumed, decisionSource, recommendationId }, () => db.query(`INSERT INTO meals
        (id,patient_id,meal_name,description,announced_carbs_g,planned_eating_at,status,actual_eating_at,
         consumed_carbs_g,decision_source,recommendation_id,confirmation_provenance,legacy_payload)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)`, [item.id, user.id, mealName,
        description, announced, plannedAt, status, actualAt, consumed,
        decisionSource, recommendationId,
        JSON.stringify(status === 'eaten' ? { source: item.confirmAnnouncedAmount === true ? 'patient_confirmed_announced' : 'patient_entered_actual' } : {}), JSON.stringify(withoutLocalSyncMetadata(item))]));
    } else throw new ApiError(404, 'Unknown record type');
    if (created) await audit(db, user.id, `${kind}.created`, kind, item.id);
    return { ok: true };
  });
}

export async function updateMeal(pool, id, input, user) {
  if (user.role !== 'patient') throw new ApiError(403, 'Patient access required');
  if (typeof input.mutationId !== 'string' || !input.mutationId.trim()) throw new ApiError(400, 'mutationId is required for retry-safe updates');
  if (!Number.isInteger(input.expectedVersion) || input.expectedVersion < 1) throw new ApiError(400, 'expectedVersion must be a positive integer');
  const mutationHash = contentHash(input);
  return withTransaction(pool, async (db) => {
    let row = (await db.query('SELECT * FROM meals WHERE id=$1 FOR UPDATE', [id])).rows[0];
    if (!row) throw new ApiError(404, 'Meal not found');
    if (row.patient_id !== user.id) throw new ApiError(403, 'Record is not available to this account');
    const retried = (await db.query('SELECT mutation_hash FROM meal_revisions WHERE meal_id=$1 AND mutation_id=$2', [id, input.mutationId])).rows[0];
    if (retried) {
      if (retried.mutation_hash !== mutationHash) throw new ApiError(409, 'mutationId was already used for a different update');
      return { ok: true, meal: mealJson(row) };
    }
    if (row.version !== input.expectedVersion) throw new ApiError(409, `Meal has changed; retry with version ${row.version}`);

    const status = input.status ?? row.status;
    if (!['planned', 'eaten', 'cancelled'].includes(status)) throw new ApiError(400, 'Meal status must be planned, eaten, or cancelled');
    if (row.status !== 'planned' && status !== row.status) throw new ApiError(409, 'Only a planned meal can transition to eaten or cancelled');
    const announced = input.announcedCarbsG === undefined
      ? row.announced_carbs_g === null ? null : Number(row.announced_carbs_g)
      : finiteNonnegative(input.announcedCarbsG, 'Announced carbohydrates');
    const plannedAt = input.plannedEatingAt === undefined
      ? row.planned_eating_at.toISOString() : timestamp(input.plannedEatingAt, 'Meal plannedEatingAt');
    let actualAt = null;
    let consumed = null;
    let provenance = {};
    if (status === 'eaten') {
      actualAt = input.actualEatingAt === undefined && row.actual_eating_at
        ? row.actual_eating_at.toISOString() : timestamp(input.actualEatingAt, 'Meal actualEatingAt');
      if (input.confirmAnnouncedAmount === true) {
        if (announced === null) throw new ApiError(400, 'Cannot confirm a missing announced carbohydrate amount');
        consumed = announced;
        provenance = { source: 'patient_confirmed_announced', mutationId: input.mutationId };
      } else if (input.consumedCarbsG !== undefined) {
        consumed = finiteNonnegative(input.consumedCarbsG, 'Consumed carbohydrates');
        provenance = { source: 'patient_entered_actual', mutationId: input.mutationId };
      } else if (row.status === 'eaten' && row.consumed_carbs_g !== null) {
        consumed = Number(row.consumed_carbs_g);
        provenance = row.confirmation_provenance || {};
      } else throw new ApiError(400, 'An eaten meal requires consumedCarbsG or confirmAnnouncedAmount=true');
    } else if (input.actualEatingAt != null || input.consumedCarbsG != null || input.confirmAnnouncedAmount === true) {
      throw new ApiError(400, 'Planned and cancelled meals cannot contain confirmed consumption or an actual eating time');
    }

    const previous = {
      status: row.status, mealName: row.meal_name, description: row.description,
      announcedCarbsG: row.announced_carbs_g === null ? null : Number(row.announced_carbs_g),
      consumedCarbsG: row.consumed_carbs_g === null ? null : Number(row.consumed_carbs_g),
      plannedEatingAt: row.planned_eating_at.toISOString(), actualEatingAt: row.actual_eating_at?.toISOString() || null,
      confirmationProvenance: row.confirmation_provenance || {},
    };
    await db.query(`INSERT INTO meal_revisions
      (id,meal_id,patient_id,changed_by_user_id,mutation_id,mutation_hash,from_version,to_version,previous_values,change_reason)
      VALUES($1,$2,$3,$3,$4,$5,$6,$7,$8,$9)`, [newId('mealrev'), id, user.id, input.mutationId, mutationHash,
      row.version, row.version + 1, JSON.stringify(previous), input.changeReason || null]);
    row = (await db.query(`UPDATE meals SET meal_name=$2,description=$3,announced_carbs_g=$4,
      planned_eating_at=$5,status=$6,actual_eating_at=$7,consumed_carbs_g=$8,
      confirmation_provenance=$9,version=version+1 WHERE id=$1 RETURNING *`, [id,
      input.meal ?? row.meal_name, input.items ?? input.description ?? row.description, announced,
      plannedAt, status, actualAt, consumed, JSON.stringify(provenance)])).rows[0];
    await audit(db, user.id, 'food.updated', 'food', id, {
      fromVersion: row.version - 1, toVersion: row.version, mutationId: input.mutationId, transition: `${previous.status}->${status}`,
    });
    return { ok: true, meal: mealJson(row) };
  });
}

export async function addMessage(pool, item, user) {
  if (!item?.id || !item?.patientSlug) throw new ApiError(400, 'Message ID and patient are required');
  if (item.from !== user.role) throw new ApiError(403, 'Invalid sender');
  return withTransaction(pool, async (db) => {
    await db.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', [`messages:${item.id}`]);
    const assignment = await currentAcceptedAssignment(db, item.patientSlug);
    if (!assignment || (user.role === 'doctor' ? assignment.doctor_id !== user.id : item.patientSlug !== user.id)) {
      throw new ApiError(403, 'Messaging opens after doctor acceptance');
    }
    let conversation = (await db.query(`SELECT * FROM conversations WHERE assignment_id=$1`, [assignment.id])).rows[0];
    if (!conversation) conversation = (await db.query(`INSERT INTO conversations(id,patient_id,doctor_id,assignment_id,status)
      VALUES($1,$2,$3,$4,'active') RETURNING *`, [newId('conversation'), item.patientSlug, assignment.doctor_id, assignment.id])).rows[0];
    const sentAt = item.sentAt ? timestamp(item.sentAt, 'Message sentAt') : null;
    const existing = (await db.query('SELECT conversation_id,sender_id,body,sent_at FROM messages WHERE id=$1', [item.id])).rows[0];
    if (existing) {
      if (existing.conversation_id === conversation.id && existing.sender_id === user.id && existing.body === item.text
        && (sentAt === null || sameInstant(existing.sent_at, sentAt))) return { ok: true };
      throw new ApiError(409, 'Existing ID conflicts with different conversation or content');
    }
    await db.query(`INSERT INTO messages(id,conversation_id,sender_id,body,sent_at,is_read,legacy_payload)
      VALUES($1,$2,$3,$4,$5,$6,$7)`, [item.id, conversation.id, user.id, item.text,
      sentAt || new Date(), item.unread === false, JSON.stringify(withoutLocalSyncMetadata(item))]);
    await audit(db, user.id, 'message.created', 'message', item.id, { conversationId: conversation.id });
    return { ok: true };
  });
}

export async function rateDoctor(pool, patientId, doctorId, score) {
  if (!Number.isInteger(score) || score < 1 || score > 5) throw new ApiError(400, 'Invalid rating');
  return withTransaction(pool, async (db) => {
    const profile = (await db.query('SELECT selected_doctor_id FROM patient_profiles WHERE user_id=$1', [patientId])).rows[0];
    if (profile?.selected_doctor_id !== doctorId) throw new ApiError(400, 'Invalid rating');
    await db.query(`INSERT INTO doctor_ratings(id,doctor_id,patient_id,score,source)
      VALUES($1,$2,$3,$4,'patient') ON CONFLICT(doctor_id,patient_id) WHERE source='patient'
      DO UPDATE SET score=EXCLUDED.score, updated_at=now()`, [newId('rating'), doctorId, patientId, score]);
    await audit(db, patientId, 'doctor_rating.updated', 'doctor', doctorId, { score });
    return (await doctorDirectory(db, patientId)).ratings;
  });
}

export async function emergencyContacts(db, patientId) {
  return (await db.query(`SELECT id, contact_name "contactName", relationship, phone_number "phoneNumber",
    is_primary "isPrimary", created_at "createdAt", updated_at "updatedAt"
    FROM patient_emergency_contacts WHERE patient_id=$1 ORDER BY is_primary DESC, created_at`, [patientId])).rows;
}

export async function createEmergencyContact(pool, patientId, input) {
  return withTransaction(pool, async (db) => {
    if (typeof input.contactName !== 'string' || !input.contactName.trim() || typeof input.relationship !== 'string' || !input.relationship.trim() || typeof input.phoneNumber !== 'string') throw new ApiError(400, 'Contact name, relationship, and phone number are required');
    if (!/^\+[1-9][0-9]{5,14}$/.test(input.phoneNumber)) throw new ApiError(400, 'Phone number must include a country code, for example +201001234567');
    if (input.isPrimary) await db.query('UPDATE patient_emergency_contacts SET is_primary=false WHERE patient_id=$1 AND is_primary', [patientId]);
    const id = input.id || newId('contact');
    const row = (await db.query(`INSERT INTO patient_emergency_contacts(id,patient_id,contact_name,relationship,phone_number,is_primary)
      VALUES($1,$2,$3,$4,$5,$6) RETURNING *`, [id, patientId, input.contactName.trim(), input.relationship.trim(), input.phoneNumber, Boolean(input.isPrimary)])).rows[0];
    await audit(db, patientId, 'emergency_contact.created', 'emergency_contact', id);
    return row;
  });
}

export async function updateEmergencyContact(pool, patientId, id, input) {
  return withTransaction(pool, async (db) => {
    if (input.contactName !== undefined && (typeof input.contactName !== 'string' || !input.contactName.trim())) throw new ApiError(400, 'Contact name cannot be blank');
    if (input.relationship !== undefined && (typeof input.relationship !== 'string' || !input.relationship.trim())) throw new ApiError(400, 'Relationship cannot be blank');
    if (input.phoneNumber !== undefined && !/^\+[1-9][0-9]{5,14}$/.test(input.phoneNumber)) throw new ApiError(400, 'Phone number must include a country code');
    if (input.isPrimary) await db.query('UPDATE patient_emergency_contacts SET is_primary=false WHERE patient_id=$1 AND id<>$2 AND is_primary', [patientId, id]);
    const row = (await db.query(`UPDATE patient_emergency_contacts SET
      contact_name=COALESCE($3,contact_name), relationship=COALESCE($4,relationship),
      phone_number=COALESCE($5,phone_number), is_primary=COALESCE($6,is_primary)
      WHERE patient_id=$1 AND id=$2 RETURNING *`, [patientId, id, input.contactName?.trim() ?? null,
      input.relationship?.trim() ?? null, input.phoneNumber ?? null, input.isPrimary ?? null])).rows[0];
    if (!row) throw new ApiError(404, 'Emergency contact not found');
    await audit(db, patientId, 'emergency_contact.updated', 'emergency_contact', id);
    return row;
  });
}

export async function deleteEmergencyContact(pool, patientId, id) {
  return withTransaction(pool, async (db) => {
    if (!(await db.query('DELETE FROM patient_emergency_contacts WHERE patient_id=$1 AND id=$2', [patientId, id])).rowCount) throw new ApiError(404, 'Emergency contact not found');
    await audit(db, patientId, 'emergency_contact.deleted', 'emergency_contact', id);
    return { ok: true };
  });
}
