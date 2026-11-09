import { ApiError, newId, optionalNumber, strictUnit, timestamp } from './lib.mjs';
import { withTransaction } from './db.mjs';

const text = (value) => value === undefined || value === null ? '' : String(value);

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

export async function updateProfile(db, userId, role, profile = {}) {
  if (role === 'patient') {
    await db.query(`INSERT INTO patient_profiles(
      user_id, full_name, age_years, weight_kg, height_cm, diabetes_type, insulin_plan,
      diagnosis_year, medications, allergies, legacy_emergency_contact, selected_doctor_id
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
    ON CONFLICT (user_id) DO UPDATE SET
      full_name=EXCLUDED.full_name, age_years=EXCLUDED.age_years, weight_kg=EXCLUDED.weight_kg,
      height_cm=EXCLUDED.height_cm, diabetes_type=EXCLUDED.diabetes_type,
      insulin_plan=EXCLUDED.insulin_plan, diagnosis_year=EXCLUDED.diagnosis_year,
      medications=EXCLUDED.medications, allergies=EXCLUDED.allergies,
      legacy_emergency_contact=EXCLUDED.legacy_emergency_contact,
      selected_doctor_id=COALESCE(EXCLUDED.selected_doctor_id, patient_profiles.selected_doctor_id)`, [
      userId, profile.fullName || 'Patient', optionalNumber(profile.age), optionalNumber(profile.weight),
      optionalNumber(profile.height), profile.diabetesType || null, profile.insulinPlan || null,
      optionalNumber(profile.diagnosisYear), profile.medications || null, profile.allergies || null,
      profile.emergencyContact || null, profile.selectedDoctorId || null,
    ]);
  } else {
    await db.query(`INSERT INTO doctor_profiles(
      user_id, full_name, specialty, years_experience, medical_school, qualifications,
      bio, certificates, papers, photo, documents
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
    ON CONFLICT (user_id) DO UPDATE SET
      full_name=EXCLUDED.full_name, specialty=EXCLUDED.specialty,
      years_experience=EXCLUDED.years_experience, medical_school=EXCLUDED.medical_school,
      qualifications=EXCLUDED.qualifications, bio=EXCLUDED.bio, certificates=EXCLUDED.certificates,
      papers=EXCLUDED.papers, photo=EXCLUDED.photo, documents=EXCLUDED.documents`, [
      userId, profile.fullName || 'Doctor', profile.specialty || null, optionalNumber(profile.yearsExperience),
      profile.medicalSchool || null, profile.qualifications || null, profile.bio || null,
      JSON.stringify(profile.certificates || []), JSON.stringify(profile.papers || []), profile.photo || null,
      JSON.stringify(profile.documents || []),
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

const assignmentJson = (row) => ({ patientId: row.patient_id, doctorId: row.doctor_id, status: row.status });

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
  const glucose = (await queryVisible(`SELECT * FROM glucose_readings WHERE patient_id=ANY($1::text[]) ORDER BY measured_at DESC`)).map((row) => ({
    ...(row.legacy_payload || {}), id: row.id, patientSlug: row.patient_id,
    value: Number(row.glucose_mg_dl), recordedAt: row.measured_at.toISOString(),
    time: row.legacy_payload?.time || row.measured_at.toISOString(),
  }));
  const food = (await queryVisible(`SELECT * FROM meals WHERE patient_id=ANY($1::text[]) ORDER BY planned_eating_at DESC`)).map((row) => ({
    ...(row.legacy_payload || {}), id: row.id, patientSlug: row.patient_id,
  }));
  const bolus = (await queryVisible(`SELECT * FROM insulin_doses WHERE patient_id=ANY($1::text[]) ORDER BY administered_at DESC`)).map((row) => ({
    ...(row.legacy_payload || {}), id: row.id, patientSlug: row.patient_id,
  }));
  const messages = (await db.query(`SELECT m.*, c.patient_id, c.doctor_id, sender.role sender_role
    FROM messages m JOIN conversations c ON c.id=m.conversation_id JOIN users sender ON sender.id=m.sender_id
    WHERE c.status='active' AND ${user.role === 'patient' ? 'c.patient_id=$1' : 'c.doctor_id=$1'}
    ORDER BY m.sent_at, m.id`, [user.id])).rows.map((row) => ({
      ...(row.legacy_payload || {}), id: row.id, doctorId: row.doctor_id, patientSlug: row.patient_id,
      from: row.sender_role, text: row.body, unread: !row.is_read,
      time: row.legacy_payload?.time || row.sent_at.toISOString(),
    }));
  return {
    account: accountFromRow(await accountById(db, user.id)), ...directory, patients,
    assignments: assignmentRows.map(assignmentJson), food, bolus, glucose, messages,
  };
}

export async function requestDoctor(pool, patientId, doctorId) {
  return withTransaction(pool, async (db) => {
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
  });
}

export async function respondAssignment(pool, doctorId, patientId, status) {
  if (!['accepted', 'declined'].includes(status)) throw new ApiError(400, 'Invalid assignment');
  return withTransaction(pool, async (db) => {
    const row = (await db.query(`UPDATE care_assignments SET status=$3, responded_at=now()
      WHERE patient_id=$1 AND doctor_id=$2 AND status='pending' RETURNING *`, [patientId, doctorId, status])).rows[0];
    if (!row) throw new ApiError(400, 'Invalid assignment');
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

async function idempotentInsert(db, table, id, patientId, payload, insert) {
  const existing = (await db.query(`SELECT patient_id, legacy_payload = $2::jsonb same_payload FROM ${table} WHERE id=$1`, [id, JSON.stringify(payload)])).rows[0];
  if (existing) {
    if (existing.patient_id === patientId && existing.same_payload) return false;
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
      const value = optionalNumber(item.value ?? item.glucoseMgDl);
      if (value === null) throw new ApiError(400, 'Glucose must be a finite nonnegative number');
      const measuredAt = timestamp(item.recordedAt ?? item.measuredAt, new Date());
      created = await idempotentInsert(db, 'glucose_readings', item.id, user.id, item, () => db.query(`INSERT INTO glucose_readings
        (id,patient_id,measured_at,glucose_mg_dl,source,legacy_payload) VALUES($1,$2,$3,$4,$5,$6)`,
        [item.id, user.id, measuredAt, value, item.source || 'manual', JSON.stringify(item)]));
    } else if (kind === 'bolus') {
      const units = strictUnit(item.administeredUnits ?? item.recorded, 'U', 'Administered insulin');
      const administeredAt = timestamp(item.administeredAt, new Date());
      created = await idempotentInsert(db, 'insulin_doses', item.id, user.id, item, () => db.query(`INSERT INTO insulin_doses
        (id,patient_id,administered_units,administered_at,decision_source,recommendation_id,confirmation_provenance,legacy_payload)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8)`, [item.id, user.id, units, administeredAt,
        item.decisionSource || 'user_decided', item.recommendationId || null,
        JSON.stringify(item.confirmationProvenance || { source: 'patient_log' }), JSON.stringify(item)]));
    } else if (kind === 'food') {
      const legacy = Object.hasOwn(item, 'carbs');
      const announced = legacy ? strictUnit(item.carbs, 'g', 'Announced carbohydrates') : optionalNumber(item.announcedCarbsG);
      const status = item.status && ['planned', 'eaten', 'cancelled'].includes(item.status) ? item.status : legacy ? 'eaten' : 'planned';
      const plannedAt = timestamp(item.plannedEatingAt, new Date());
      const actualAt = status === 'eaten' ? timestamp(item.actualEatingAt, new Date()) : null;
      let consumed = optionalNumber(item.consumedCarbsG);
      if (item.confirmAnnouncedAmount === true) consumed = announced;
      if (legacy) consumed = announced;
      created = await idempotentInsert(db, 'meals', item.id, user.id, item, () => db.query(`INSERT INTO meals
        (id,patient_id,meal_name,description,announced_carbs_g,planned_eating_at,status,actual_eating_at,
         consumed_carbs_g,decision_source,recommendation_id,legacy_payload)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`, [item.id, user.id, item.meal || null,
        item.items || item.description || null, announced, plannedAt, status, actualAt, consumed,
        item.decisionSource || 'user_chosen', item.recommendationId || null, JSON.stringify(item)]));
    } else throw new ApiError(404, 'Unknown record type');
    if (created) await audit(db, user.id, `${kind}.created`, kind, item.id);
    return { ok: true };
  });
}

export async function addMessage(pool, item, user) {
  if (!item?.id || !item?.patientSlug) throw new ApiError(400, 'Message ID and patient are required');
  if (item.from !== user.role) throw new ApiError(403, 'Invalid sender');
  return withTransaction(pool, async (db) => {
    const assignment = await currentAcceptedAssignment(db, item.patientSlug);
    if (!assignment || (user.role === 'doctor' ? assignment.doctor_id !== user.id : item.patientSlug !== user.id)) {
      throw new ApiError(403, 'Messaging opens after doctor acceptance');
    }
    let conversation = (await db.query(`SELECT * FROM conversations WHERE assignment_id=$1`, [assignment.id])).rows[0];
    if (!conversation) conversation = (await db.query(`INSERT INTO conversations(id,patient_id,doctor_id,assignment_id,status)
      VALUES($1,$2,$3,$4,'active') RETURNING *`, [newId('conversation'), item.patientSlug, assignment.doctor_id, assignment.id])).rows[0];
    const existing = (await db.query('SELECT conversation_id,legacy_payload = $2::jsonb same_payload FROM messages WHERE id=$1', [item.id, JSON.stringify(item)])).rows[0];
    if (existing) {
      if (existing.conversation_id === conversation.id && existing.same_payload) return { ok: true };
      throw new ApiError(409, 'Existing ID conflicts with different conversation or content');
    }
    await db.query(`INSERT INTO messages(id,conversation_id,sender_id,body,sent_at,is_read,legacy_payload)
      VALUES($1,$2,$3,$4,$5,$6,$7)`, [item.id, conversation.id, user.id, item.text,
      timestamp(item.sentAt, new Date()), item.unread === false, JSON.stringify(item)]);
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
    if (!input.contactName || !input.relationship || !input.phoneNumber) throw new ApiError(400, 'Contact name, relationship, and phone number are required');
    if (!/^\+[1-9][0-9]{5,14}$/.test(input.phoneNumber)) throw new ApiError(400, 'Phone number must include a country code, for example +201001234567');
    if (input.isPrimary) await db.query('UPDATE patient_emergency_contacts SET is_primary=false WHERE patient_id=$1 AND is_primary', [patientId]);
    const id = input.id || newId('contact');
    const row = (await db.query(`INSERT INTO patient_emergency_contacts(id,patient_id,contact_name,relationship,phone_number,is_primary)
      VALUES($1,$2,$3,$4,$5,$6) RETURNING *`, [id, patientId, input.contactName, input.relationship, input.phoneNumber, Boolean(input.isPrimary)])).rows[0];
    await audit(db, patientId, 'emergency_contact.created', 'emergency_contact', id);
    return row;
  });
}

export async function updateEmergencyContact(pool, patientId, id, input) {
  return withTransaction(pool, async (db) => {
    if (input.phoneNumber !== undefined && !/^\+[1-9][0-9]{5,14}$/.test(input.phoneNumber)) throw new ApiError(400, 'Phone number must include a country code');
    if (input.isPrimary) await db.query('UPDATE patient_emergency_contacts SET is_primary=false WHERE patient_id=$1 AND id<>$2 AND is_primary', [patientId, id]);
    const row = (await db.query(`UPDATE patient_emergency_contacts SET
      contact_name=COALESCE($3,contact_name), relationship=COALESCE($4,relationship),
      phone_number=COALESCE($5,phone_number), is_primary=COALESCE($6,is_primary)
      WHERE patient_id=$1 AND id=$2 RETURNING *`, [patientId, id, input.contactName ?? null,
      input.relationship ?? null, input.phoneNumber ?? null, input.isPrimary ?? null])).rows[0];
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
