-- doctor_ratings intentionally permits a NULL patient_id for non-patient sample/import
-- ratings. Keep the shared strict trigger on every other patient-owned table and use a
-- rating-specific function for this one exception.

DROP TRIGGER IF EXISTS doctor_ratings_patient_role ON doctor_ratings;

CREATE OR REPLACE FUNCTION enforce_rating_patient_role() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE account_role text;
BEGIN
  IF NEW.source = 'patient' AND NEW.patient_id IS NULL THEN
    RAISE EXCEPTION 'patient-submitted ratings require patient_id' USING ERRCODE='23514';
  END IF;

  IF NEW.patient_id IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT role INTO account_role FROM users WHERE id=NEW.patient_id;
  IF account_role IS DISTINCT FROM 'patient' THEN
    RAISE EXCEPTION 'patient_id must reference a patient account' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER doctor_ratings_patient_role
  BEFORE INSERT OR UPDATE ON doctor_ratings
  FOR EACH ROW EXECUTE FUNCTION enforce_rating_patient_role();
