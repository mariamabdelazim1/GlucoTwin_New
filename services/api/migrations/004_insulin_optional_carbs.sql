ALTER TABLE insulin_doses
  ADD COLUMN IF NOT EXISTS carbs_g numeric;

ALTER TABLE insulin_doses
  DROP CONSTRAINT IF EXISTS insulin_doses_carbs_g_check;
ALTER TABLE insulin_doses
  ADD CONSTRAINT insulin_doses_carbs_g_check
  CHECK (carbs_g IS NULL OR carbs_g >= 0) NOT VALID;

ALTER TABLE insulin_doses
  DROP CONSTRAINT IF EXISTS insulin_carbs_finite;
ALTER TABLE insulin_doses
  ADD CONSTRAINT insulin_carbs_finite
  CHECK (carbs_g IS NULL OR carbs_g::text NOT IN ('NaN','Infinity','-Infinity')) NOT VALID;

-- Canonicalize valid historical carbohydrate context without changing or
-- deleting the original compatibility payload (including pre-meal glucose).
UPDATE insulin_doses
SET carbs_g = ((regexp_match(legacy_payload->>'carbs',
  '^\s*(\d+(?:\.\d+)?)\s*g\s*$', 'i'))[1])::numeric
WHERE carbs_g IS NULL
  AND legacy_payload ? 'carbs'
  AND legacy_payload->>'carbs' ~* '^\s*\d+(?:\.\d+)?\s*g\s*$';

ALTER TABLE insulin_doses VALIDATE CONSTRAINT insulin_doses_carbs_g_check;
ALTER TABLE insulin_doses VALIDATE CONSTRAINT insulin_carbs_finite;
