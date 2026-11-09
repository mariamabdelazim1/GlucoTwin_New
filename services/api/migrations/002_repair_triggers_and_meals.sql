-- Repair triggers installed by 001 without rewriting migration history.
-- Each function below only references columns that exist on its target table.

DROP TRIGGER IF EXISTS recommendation_prediction_patient_consistency ON recommendations;
DROP TRIGGER IF EXISTS response_recommendation_patient_consistency ON recommendation_responses;
DROP TRIGGER IF EXISTS dose_recommendation_patient_consistency ON insulin_doses;
DROP TRIGGER IF EXISTS meal_recommendation_patient_consistency ON meals;

CREATE OR REPLACE FUNCTION enforce_recommendation_prediction_patient() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked_patient text;
BEGIN
  IF NEW.prediction_id IS NULL THEN RETURN NEW; END IF;
  SELECT patient_id INTO linked_patient FROM predictions WHERE id=NEW.prediction_id;
  IF linked_patient IS DISTINCT FROM NEW.patient_id THEN
    RAISE EXCEPTION 'Linked record belongs to a different patient' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER recommendation_prediction_patient_consistency BEFORE INSERT OR UPDATE ON recommendations
  FOR EACH ROW EXECUTE FUNCTION enforce_recommendation_prediction_patient();

CREATE OR REPLACE FUNCTION enforce_response_recommendation_patient() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked_patient text;
BEGIN
  SELECT patient_id INTO linked_patient FROM recommendations WHERE id=NEW.recommendation_id;
  IF linked_patient IS DISTINCT FROM NEW.patient_id THEN
    RAISE EXCEPTION 'Linked record belongs to a different patient' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER response_recommendation_patient_consistency BEFORE INSERT OR UPDATE ON recommendation_responses
  FOR EACH ROW EXECUTE FUNCTION enforce_response_recommendation_patient();

CREATE OR REPLACE FUNCTION enforce_dose_recommendation_patient() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked_patient text;
BEGIN
  IF NEW.recommendation_id IS NULL THEN RETURN NEW; END IF;
  SELECT patient_id INTO linked_patient FROM recommendations WHERE id=NEW.recommendation_id;
  IF linked_patient IS DISTINCT FROM NEW.patient_id THEN
    RAISE EXCEPTION 'Linked record belongs to a different patient' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER dose_recommendation_patient_consistency BEFORE INSERT OR UPDATE ON insulin_doses
  FOR EACH ROW EXECUTE FUNCTION enforce_dose_recommendation_patient();

CREATE OR REPLACE FUNCTION enforce_meal_recommendation_patient() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked_patient text;
BEGIN
  IF NEW.recommendation_id IS NULL THEN RETURN NEW; END IF;
  SELECT patient_id INTO linked_patient FROM recommendations WHERE id=NEW.recommendation_id;
  IF linked_patient IS DISTINCT FROM NEW.patient_id THEN
    RAISE EXCEPTION 'Linked record belongs to a different patient' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER meal_recommendation_patient_consistency BEFORE INSERT OR UPDATE ON meals
  FOR EACH ROW EXECUTE FUNCTION enforce_meal_recommendation_patient();

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'patient_profiles','patient_emergency_contacts','care_assignments','doctor_ratings','conversations',
    'predictions','recommendations','recommendation_responses','glucose_readings','insulin_doses',
    'basal_schedule_entries','meals'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I_patient_role ON %I', table_name, table_name);
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['doctor_profiles','care_assignments','doctor_ratings','conversations'] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS %I_doctor_role ON %I', table_name, table_name);
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION enforce_patient_profile_roles() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE account_role text;
BEGIN
  SELECT role INTO account_role FROM users WHERE id=NEW.user_id;
  IF account_role IS DISTINCT FROM 'patient' THEN
    RAISE EXCEPTION 'user_id must reference a patient account' USING ERRCODE='23514';
  END IF;
  IF NEW.selected_doctor_id IS NOT NULL THEN
    SELECT role INTO account_role FROM users WHERE id=NEW.selected_doctor_id;
    IF account_role IS DISTINCT FROM 'doctor' THEN
      RAISE EXCEPTION 'selected_doctor_id must reference a doctor account' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER patient_profiles_patient_role BEFORE INSERT OR UPDATE ON patient_profiles
  FOR EACH ROW EXECUTE FUNCTION enforce_patient_profile_roles();

CREATE OR REPLACE FUNCTION enforce_doctor_profile_role() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE account_role text;
BEGIN
  SELECT role INTO account_role FROM users WHERE id=NEW.user_id;
  IF account_role IS DISTINCT FROM 'doctor' THEN
    RAISE EXCEPTION 'user_id must reference a doctor account' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER doctor_profiles_doctor_role BEFORE INSERT OR UPDATE ON doctor_profiles
  FOR EACH ROW EXECUTE FUNCTION enforce_doctor_profile_role();

CREATE OR REPLACE FUNCTION enforce_patient_id_role() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE account_role text;
BEGIN
  SELECT role INTO account_role FROM users WHERE id=NEW.patient_id;
  IF account_role IS DISTINCT FROM 'patient' THEN
    RAISE EXCEPTION 'patient_id must reference a patient account' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION enforce_doctor_id_role() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE account_role text;
BEGIN
  SELECT role INTO account_role FROM users WHERE id=NEW.doctor_id;
  IF account_role IS DISTINCT FROM 'doctor' THEN
    RAISE EXCEPTION 'doctor_id must reference a doctor account' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'patient_emergency_contacts','care_assignments','doctor_ratings','conversations','predictions',
    'recommendations','recommendation_responses','glucose_readings','insulin_doses','basal_schedule_entries','meals'
  ] LOOP
    EXECUTE format('CREATE TRIGGER %I_patient_role BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION enforce_patient_id_role()', table_name, table_name);
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY['care_assignments','doctor_ratings','conversations'] LOOP
    EXECUTE format('CREATE TRIGGER %I_doctor_role BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION enforce_doctor_id_role()', table_name, table_name);
  END LOOP;
END $$;

ALTER TABLE meals ADD COLUMN version integer NOT NULL DEFAULT 1;
ALTER TABLE meals ADD COLUMN confirmation_provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE meals ADD CONSTRAINT meals_version_positive CHECK (version > 0);
ALTER TABLE meals ADD CONSTRAINT meals_lifecycle_valid CHECK (
  (status='planned' AND actual_eating_at IS NULL AND consumed_carbs_g IS NULL) OR
  (status='eaten' AND actual_eating_at IS NOT NULL AND consumed_carbs_g IS NOT NULL) OR
  (status='cancelled' AND actual_eating_at IS NULL AND consumed_carbs_g IS NULL)
) NOT VALID;

CREATE TABLE meal_revisions (
  id text PRIMARY KEY,
  meal_id text NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
  patient_id text NOT NULL REFERENCES users(id),
  changed_by_user_id text NOT NULL REFERENCES users(id),
  mutation_id text NOT NULL,
  mutation_hash text NOT NULL,
  from_version integer NOT NULL CHECK (from_version > 0),
  to_version integer NOT NULL CHECK (to_version = from_version + 1),
  previous_values jsonb NOT NULL,
  change_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (meal_id, mutation_id)
);
CREATE INDEX meal_revisions_meal_time_idx ON meal_revisions(meal_id, created_at DESC);
CREATE TRIGGER meal_revisions_patient_role BEFORE INSERT OR UPDATE ON meal_revisions
  FOR EACH ROW EXECUTE FUNCTION enforce_patient_id_role();

-- PostgreSQL numeric accepts NaN and infinities; these NOT VALID constraints protect
-- all future direct writes while allowing existing rows to be reviewed before validation.
ALTER TABLE patient_profiles ADD CONSTRAINT patient_weight_finite CHECK (weight_kg IS NULL OR weight_kg::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
ALTER TABLE patient_profiles ADD CONSTRAINT patient_height_finite CHECK (height_cm IS NULL OR height_cm::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
ALTER TABLE prediction_points ADD CONSTRAINT prediction_glucose_finite CHECK (glucose_mg_dl::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
ALTER TABLE recommendations ADD CONSTRAINT recommendation_amount_finite CHECK (suggested_amount IS NULL OR suggested_amount::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
ALTER TABLE glucose_readings ADD CONSTRAINT glucose_value_finite CHECK (glucose_mg_dl::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
ALTER TABLE insulin_doses ADD CONSTRAINT insulin_units_finite CHECK (administered_units::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
ALTER TABLE basal_schedule_entries ADD CONSTRAINT basal_rate_finite CHECK (rate_u_per_hour::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
ALTER TABLE meals ADD CONSTRAINT meal_announced_finite CHECK (announced_carbs_g IS NULL OR announced_carbs_g::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
ALTER TABLE meals ADD CONSTRAINT meal_consumed_finite CHECK (consumed_carbs_g IS NULL OR consumed_carbs_g::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;
