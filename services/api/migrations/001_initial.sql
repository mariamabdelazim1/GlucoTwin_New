CREATE TABLE IF NOT EXISTS schema_migrations (
  version text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id text PRIMARY KEY,
  role text NOT NULL CHECK (role IN ('patient', 'doctor')),
  email text NOT NULL,
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (length(trim(id)) > 0),
  CHECK (length(trim(email)) > 3)
);
CREATE UNIQUE INDEX users_email_lower_unique ON users (lower(email));

CREATE TABLE patient_profiles (
  user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  full_name text NOT NULL,
  age_years integer CHECK (age_years IS NULL OR age_years >= 0),
  weight_kg numeric CHECK (weight_kg IS NULL OR weight_kg >= 0),
  height_cm numeric CHECK (height_cm IS NULL OR height_cm >= 0),
  diabetes_type text,
  insulin_plan text,
  diagnosis_year integer,
  medications text,
  allergies text,
  legacy_emergency_contact text,
  selected_doctor_id text REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE doctor_profiles (
  user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  full_name text NOT NULL,
  specialty text,
  years_experience integer CHECK (years_experience IS NULL OR years_experience >= 0),
  medical_school text,
  qualifications text,
  bio text,
  certificates jsonb NOT NULL DEFAULT '[]'::jsonb,
  papers jsonb NOT NULL DEFAULT '[]'::jsonb,
  photo text,
  documents jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE patient_emergency_contacts (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  contact_name text NOT NULL,
  relationship text NOT NULL,
  phone_number text NOT NULL,
  is_primary boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (length(trim(contact_name)) > 0),
  CHECK (length(trim(relationship)) > 0),
  CHECK (phone_number ~ '^\+[1-9][0-9]{5,14}$')
);
CREATE INDEX emergency_contacts_patient_idx ON patient_emergency_contacts(patient_id, created_at);
CREATE UNIQUE INDEX emergency_contacts_one_primary_idx
  ON patient_emergency_contacts(patient_id) WHERE is_primary;

CREATE TABLE care_assignments (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id),
  doctor_id text NOT NULL REFERENCES users(id),
  status text NOT NULL CHECK (status IN ('pending', 'accepted', 'declined', 'ended')),
  requested_at timestamptz NOT NULL DEFAULT now(),
  responded_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (patient_id <> doctor_id),
  CHECK ((status = 'ended') = (ended_at IS NOT NULL))
);
CREATE INDEX care_assignments_patient_history_idx ON care_assignments(patient_id, requested_at DESC);
CREATE INDEX care_assignments_doctor_history_idx ON care_assignments(doctor_id, requested_at DESC);
CREATE UNIQUE INDEX care_assignments_one_current_patient_idx
  ON care_assignments(patient_id) WHERE status IN ('pending', 'accepted');

CREATE TABLE doctor_ratings (
  id text PRIMARY KEY,
  doctor_id text NOT NULL REFERENCES users(id),
  patient_id text REFERENCES users(id),
  score integer NOT NULL CHECK (score BETWEEN 1 AND 5),
  source text NOT NULL CHECK (source IN ('patient', 'demo', 'imported')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((source = 'patient' AND patient_id IS NOT NULL) OR source <> 'patient')
);
CREATE INDEX doctor_ratings_doctor_idx ON doctor_ratings(doctor_id, created_at DESC);
CREATE UNIQUE INDEX doctor_ratings_patient_unique_idx
  ON doctor_ratings(doctor_id, patient_id) WHERE source = 'patient';

CREATE TABLE conversations (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id),
  doctor_id text NOT NULL REFERENCES users(id),
  assignment_id text NOT NULL UNIQUE REFERENCES care_assignments(id),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'ended')),
  created_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  CHECK ((status = 'ended') = (ended_at IS NOT NULL))
);
CREATE INDEX conversations_patient_idx ON conversations(patient_id, created_at DESC);
CREATE INDEX conversations_doctor_idx ON conversations(doctor_id, created_at DESC);

CREATE TABLE messages (
  id text PRIMARY KEY,
  conversation_id text NOT NULL REFERENCES conversations(id),
  sender_id text NOT NULL REFERENCES users(id),
  body text NOT NULL,
  sent_at timestamptz NOT NULL DEFAULT now(),
  is_read boolean NOT NULL DEFAULT false,
  legacy_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (length(body) > 0)
);
CREATE INDEX messages_conversation_time_idx ON messages(conversation_id, sent_at, id);

CREATE TABLE predictions (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id),
  requested_by_user_id text NOT NULL REFERENCES users(id),
  forecast_origin_at timestamptz NOT NULL,
  generated_at timestamptz,
  model_version text,
  checkpoint_version text,
  horizon_minutes integer CHECK (horizon_minutes IS NULL OR horizon_minutes > 0),
  interval_minutes integer CHECK (interval_minutes IS NULL OR interval_minutes > 0),
  scenario_inputs jsonb NOT NULL DEFAULT '{}'::jsonb,
  future_input_assumptions jsonb NOT NULL DEFAULT '{}'::jsonb,
  input_snapshot jsonb NOT NULL,
  input_snapshot_sha256 text NOT NULL,
  status text NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  failure_code text,
  failure_detail text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX predictions_patient_origin_idx ON predictions(patient_id, forecast_origin_at DESC);

CREATE TABLE prediction_points (
  prediction_id text NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
  point_index integer NOT NULL CHECK (point_index >= 0),
  predicted_at timestamptz NOT NULL,
  glucose_mg_dl numeric NOT NULL CHECK (glucose_mg_dl >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (prediction_id, point_index),
  UNIQUE (prediction_id, predicted_at)
);

CREATE TABLE recommendations (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id),
  prediction_id text REFERENCES predictions(id),
  recommendation_type text NOT NULL CHECK (recommendation_type IN ('bolus', 'basal', 'nutrition')),
  suggested_amount numeric CHECK (suggested_amount IS NULL OR suggested_amount >= 0),
  suggested_unit text,
  suggested_schedule jsonb,
  suggested_meal jsonb,
  model_version text,
  checkpoint_version text,
  validation_status text NOT NULL DEFAULT 'pending'
    CHECK (validation_status IN ('pending', 'passed', 'failed', 'unavailable')),
  validation_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  experimental_disclaimer text NOT NULL DEFAULT 'Experimental recommendation; not clinically validated as safe.',
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (prediction_id IS NULL OR length(prediction_id) > 0)
);
CREATE INDEX recommendations_patient_time_idx ON recommendations(patient_id, created_at DESC);

CREATE TABLE recommendation_responses (
  id text PRIMARY KEY,
  recommendation_id text NOT NULL REFERENCES recommendations(id),
  patient_id text NOT NULL REFERENCES users(id),
  response text NOT NULL CHECK (response IN ('pending', 'accepted', 'modified', 'declined')),
  modified_value jsonb,
  responded_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX recommendation_responses_history_idx
  ON recommendation_responses(recommendation_id, responded_at DESC);

CREATE TABLE glucose_readings (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id),
  measured_at timestamptz NOT NULL,
  glucose_mg_dl numeric NOT NULL CHECK (glucose_mg_dl >= 0),
  source text NOT NULL CHECK (source IN ('manual', 'cgm', 'demo', 'imported')),
  legacy_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX glucose_patient_time_idx ON glucose_readings(patient_id, measured_at DESC);

CREATE TABLE insulin_doses (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id),
  administered_units numeric NOT NULL CHECK (administered_units >= 0),
  administered_at timestamptz NOT NULL,
  decision_source text NOT NULL CHECK (decision_source IN ('user_decided', 'ai_followed', 'ai_modified', 'doctor_directed')),
  recommendation_id text REFERENCES recommendations(id),
  confirmation_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  legacy_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX insulin_patient_time_idx ON insulin_doses(patient_id, administered_at DESC);

CREATE TABLE basal_schedule_entries (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id),
  rate_u_per_hour numeric NOT NULL CHECK (rate_u_per_hour >= 0),
  effective_from timestamptz NOT NULL,
  effective_to timestamptz,
  timezone text NOT NULL,
  schedule_kind text NOT NULL CHECK (schedule_kind IN ('prescribed_planned', 'confirmed_delivery')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE INDEX basal_patient_effective_idx ON basal_schedule_entries(patient_id, effective_from DESC);

CREATE TABLE meals (
  id text PRIMARY KEY,
  patient_id text NOT NULL REFERENCES users(id),
  meal_name text,
  description text,
  announced_carbs_g numeric CHECK (announced_carbs_g IS NULL OR announced_carbs_g >= 0),
  planned_eating_at timestamptz NOT NULL,
  status text NOT NULL CHECK (status IN ('planned', 'eaten', 'cancelled')),
  actual_eating_at timestamptz,
  consumed_carbs_g numeric CHECK (consumed_carbs_g IS NULL OR consumed_carbs_g >= 0),
  decision_source text NOT NULL CHECK (decision_source IN ('user_chosen', 'ai_followed', 'ai_modified', 'doctor_directed')),
  recommendation_id text REFERENCES recommendations(id),
  legacy_payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((status = 'eaten' AND actual_eating_at IS NOT NULL) OR status <> 'eaten'),
  CHECK (status <> 'cancelled' OR actual_eating_at IS NULL)
);
CREATE INDEX meals_patient_planned_idx ON meals(patient_id, planned_eating_at DESC);
CREATE INDEX meals_patient_actual_idx ON meals(patient_id, actual_eating_at DESC) WHERE actual_eating_at IS NOT NULL;

CREATE TABLE audit_events (
  id text PRIMARY KEY,
  actor_user_id text REFERENCES users(id),
  event_type text NOT NULL,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_entity_idx ON audit_events(entity_type, entity_id, created_at DESC);
CREATE INDEX audit_events_actor_idx ON audit_events(actor_user_id, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'users', 'patient_profiles', 'doctor_profiles', 'patient_emergency_contacts',
    'care_assignments', 'doctor_ratings', 'predictions', 'glucose_readings',
    'insulin_doses', 'basal_schedule_entries', 'meals'
  ] LOOP
    EXECUTE format('CREATE TRIGGER %I_set_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()', table_name, table_name);
  END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION prevent_basal_overlap() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(NEW.patient_id || ':' || NEW.schedule_kind, 0));
  IF EXISTS (
    SELECT 1 FROM basal_schedule_entries existing
    WHERE existing.patient_id = NEW.patient_id
      AND existing.schedule_kind = NEW.schedule_kind
      AND existing.id <> NEW.id
      AND tstzrange(existing.effective_from, COALESCE(existing.effective_to, 'infinity'::timestamptz), '[)')
          && tstzrange(NEW.effective_from, COALESCE(NEW.effective_to, 'infinity'::timestamptz), '[)')
  ) THEN
    RAISE EXCEPTION 'Overlapping basal schedule entry for patient and schedule kind' USING ERRCODE = '23P01';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER basal_schedule_no_overlap
  BEFORE INSERT OR UPDATE ON basal_schedule_entries
  FOR EACH ROW EXECUTE FUNCTION prevent_basal_overlap();

CREATE OR REPLACE FUNCTION enforce_linked_patient_consistency() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked_patient text;
BEGIN
  IF TG_TABLE_NAME = 'recommendations' AND NEW.prediction_id IS NOT NULL THEN
    SELECT patient_id INTO linked_patient FROM predictions WHERE id = NEW.prediction_id;
  ELSIF TG_TABLE_NAME = 'recommendation_responses' THEN
    SELECT patient_id INTO linked_patient FROM recommendations WHERE id = NEW.recommendation_id;
  ELSIF TG_TABLE_NAME = 'insulin_doses' AND NEW.recommendation_id IS NOT NULL THEN
    SELECT patient_id INTO linked_patient FROM recommendations WHERE id = NEW.recommendation_id;
  ELSIF TG_TABLE_NAME = 'meals' AND NEW.recommendation_id IS NOT NULL THEN
    SELECT patient_id INTO linked_patient FROM recommendations WHERE id = NEW.recommendation_id;
  ELSE
    RETURN NEW;
  END IF;
  IF linked_patient IS DISTINCT FROM NEW.patient_id THEN
    RAISE EXCEPTION 'Linked record belongs to a different patient' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER recommendation_prediction_patient_consistency
  BEFORE INSERT OR UPDATE ON recommendations FOR EACH ROW EXECUTE FUNCTION enforce_linked_patient_consistency();
CREATE TRIGGER response_recommendation_patient_consistency
  BEFORE INSERT OR UPDATE ON recommendation_responses FOR EACH ROW EXECUTE FUNCTION enforce_linked_patient_consistency();
CREATE TRIGGER dose_recommendation_patient_consistency
  BEFORE INSERT OR UPDATE ON insulin_doses FOR EACH ROW EXECUTE FUNCTION enforce_linked_patient_consistency();
CREATE TRIGGER meal_recommendation_patient_consistency
  BEFORE INSERT OR UPDATE ON meals FOR EACH ROW EXECUTE FUNCTION enforce_linked_patient_consistency();

CREATE OR REPLACE FUNCTION enforce_message_participant() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE participant boolean;
BEGIN
  SELECT NEW.sender_id IN (patient_id, doctor_id) INTO participant
  FROM conversations WHERE id = NEW.conversation_id;
  IF participant IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'Message sender is not a conversation participant' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER message_sender_participant
  BEFORE INSERT OR UPDATE ON messages FOR EACH ROW EXECUTE FUNCTION enforce_message_participant();

CREATE OR REPLACE FUNCTION enforce_patient_role() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_id text; target_role text;
BEGIN
  target_id := CASE WHEN TG_TABLE_NAME = 'patient_profiles' THEN NEW.user_id ELSE NEW.patient_id END;
  IF target_id IS NULL THEN RETURN NEW; END IF;
  SELECT role INTO target_role FROM users WHERE id = target_id;
  IF target_role IS DISTINCT FROM 'patient' THEN
    RAISE EXCEPTION 'patient_id must reference a patient account' USING ERRCODE = '23514';
  END IF;
  IF TG_TABLE_NAME = 'patient_profiles' AND NEW.selected_doctor_id IS NOT NULL THEN
    SELECT role INTO target_role FROM users WHERE id = NEW.selected_doctor_id;
    IF target_role IS DISTINCT FROM 'doctor' THEN
      RAISE EXCEPTION 'selected_doctor_id must reference a doctor account' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_doctor_role() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_id text; target_role text;
BEGIN
  target_id := CASE WHEN TG_TABLE_NAME = 'doctor_profiles' THEN NEW.user_id ELSE NEW.doctor_id END;
  SELECT role INTO target_role FROM users WHERE id = target_id;
  IF target_role IS DISTINCT FROM 'doctor' THEN
    RAISE EXCEPTION 'doctor_id must reference a doctor account' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'patient_profiles', 'patient_emergency_contacts', 'care_assignments', 'doctor_ratings',
    'conversations', 'predictions', 'recommendations', 'recommendation_responses',
    'glucose_readings', 'insulin_doses', 'basal_schedule_entries', 'meals'
  ] LOOP
    EXECUTE format('CREATE TRIGGER %I_patient_role BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION enforce_patient_role()', table_name, table_name);
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['doctor_profiles', 'care_assignments', 'doctor_ratings', 'conversations'] LOOP
    EXECUTE format('CREATE TRIGGER %I_doctor_role BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION enforce_doctor_role()', table_name, table_name);
  END LOOP;
END;
$$;
