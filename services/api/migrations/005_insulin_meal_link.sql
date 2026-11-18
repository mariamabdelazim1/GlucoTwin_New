ALTER TABLE insulin_doses
  ADD COLUMN IF NOT EXISTS meal_id text REFERENCES meals(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS insulin_meal_idx
  ON insulin_doses(meal_id) WHERE meal_id IS NOT NULL;

CREATE OR REPLACE FUNCTION enforce_dose_meal_patient() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked_patient text;
BEGIN
  IF NEW.meal_id IS NULL THEN RETURN NEW; END IF;
  SELECT patient_id INTO linked_patient FROM meals WHERE id=NEW.meal_id;
  IF linked_patient IS DISTINCT FROM NEW.patient_id THEN
    RAISE EXCEPTION 'Linked meal belongs to a different patient' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER dose_meal_patient_consistency
  BEFORE INSERT OR UPDATE OF meal_id, patient_id ON insulin_doses
  FOR EACH ROW EXECUTE FUNCTION enforce_dose_meal_patient();
