# GlucoTwin application API

The Node ESM API stores application data in PostgreSQL through the small `pg` driver. SQL migrations remain explicit and reviewable; no ORM or backend rewrite was introduced. The server requires `DATABASE_URL` and never falls back to JSON persistence.

## Local setup

From the repository root:

```bash
cp .env.example .env
docker compose up -d postgres
npm install
npm run db:migrate
npm run db:seed
npm run dev:api
```

`db:seed` is explicit, idempotent development data. Production startup never creates demo accounts or records. Change every example credential and `TOKEN_SECRET` outside local development.

For a legacy-data migration, run `db:migrate` and then `db:import` on an otherwise unseeded target database. Do not seed first: the importer deliberately rejects an existing ID whose password hash or content differs instead of overwriting it.

If the named Docker volume existed before the test-database initialization file was added, create the test database once without deleting the volume:

```bash
docker compose exec postgres createdb -U glucotwin glucotwin_test
```

## Database commands

```bash
# Development migrations
npm run db:migrate

# Explicit development demo seed
npm run db:seed

# Atomic legacy JSON import; the source file is never modified
npm run db:import -- /absolute/path/to/data.json

# Migrate, seed, and test only TEST_DATABASE_URL
npm run test:api
```

The import performs a complete validation pass before opening its transaction. Ambiguous human-readable amounts or records without reproducible event timestamps are reported and leave the database unchanged. Known synthetic fixture IDs use the fixture's documented 2026-01-01 date. Existing password hashes are preserved.

## Schema

Identity and care:

- `users`, `patient_profiles`, `doctor_profiles`
- `patient_emergency_contacts` (partial unique index permits at most one primary contact per patient)
- `care_assignments` with pending, accepted, declined, and ended history
- `doctor_ratings`

Communication:

- `conversations`, each bound to the assignment that created it
- `messages`, including sender, server timestamp, and read state

Medical events:

- `glucose_readings` in mg/dL
- `insulin_doses` in units; these are actual administrations, never hypothetical scenarios
- `basal_schedule_entries` in U/hour with prescribed-versus-confirmed kind and overlap prevention
- `meals`, separating announced carbohydrates from nullable confirmed consumption

Model-history foundation (storage only; no inference endpoints):

- `predictions`, `prediction_points`
- `recommendations`, `recommendation_responses`

Traceability:

- `audit_events`, containing identifiers and action metadata but not passwords, tokens, message bodies, or medical payloads

All event times use `timestamptz`. Database triggers enforce patient consistency across linked predictions, recommendations, responses, meals, and administered doses. Accepting a recommendation inserts only a response; it never creates an insulin dose or meal.

## Access and conversation history

The current one-doctor workflow is preserved. Requesting a different doctor ends the former active assignment and conversation before creating the new pending assignment. Records are retained for history, but the snapshot API exposes messages only from the current active conversation. Therefore a newly assigned doctor cannot see a former doctor's conversation, and the former doctor loses snapshot access after reassignment. A future audited history endpoint can expose retained conversations under a separately approved policy.

## Compatibility and limitations

Existing `/api` response shapes are retained for the React and Flutter clients. Legacy food and bolus routes accept only strict values such as `20g` and `2 U`; their original payload is retained while normalized columns support future model-input preparation. New meal payloads preserve `consumedCarbsG: null`; `confirmAnnouncedAmount: true` is required to copy an announced amount into confirmed consumption.

The existing admin screens still use frontend/demo state. This migration does not create an admin role, an admin provisioning API, or broad administrative access. New doctor accounts cannot be self-registered through `/api/auth/bridge`; they must be explicitly provisioned in a controlled process.

Durable offline conflict resolution is not claimed. Client-provided IDs make retries idempotent, while conflicting ownership or content returns HTTP 409.
