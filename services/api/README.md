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

`db:migrate` is also the upgrade command for an existing database. It records and skips
previously applied migrations, then applies `003_rating_patient_role.sql`; do not reset or
recreate the database. For migration regression setup only, the runner supports
`node scripts/migrate.mjs --test --through=002_repair_triggers_and_meals.sql` against the dedicated
`TEST_DATABASE_URL`.

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

Patient-submitted ratings require a valid patient account. Demo and imported ratings may
use a null `patient_id`; if they supply a non-null ID, it must still reference a patient.

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

Medical event timestamps sent to the API must be complete ISO 8601 values ending in
`Z` or an explicit offset, for example `2026-11-09T10:15:00Z` or
`2026-11-09T12:15:00+02:00`. Glucose requires `recordedAt`, insulin requires
`administeredAt`, and meals require `plannedEatingAt` plus `actualEatingAt` when eaten.
The clients capture these once when the patient logs or confirms the event, so a retry
does not turn network receipt time into medical event time.

## Meal lifecycle and updates

Valid normalized combinations are:

- `planned`: `actualEatingAt` and `consumedCarbsG` are null.
- `eaten`: both fields are present. `consumedCarbsG` may be zero. Send either an
  explicit value or `confirmAnnouncedAmount: true` to copy the announced amount.
- `cancelled`: both fields are null. A partially eaten meal is `eaten` with the actual
  partial amount, not `cancelled`.

Creating a planned meal (the legacy `carbs` string remains supported but is announcement
only):

```http
POST /api/food
Authorization: Bearer TOKEN
Content-Type: application/json

{"id":"meal-client-1","patientSlug":"patient-1","carbs":"45g","status":"planned","plannedEatingAt":"2026-11-09T18:00:00+02:00"}
```

Confirm it without retyping the amount:

```http
PATCH /api/food/meal-client-1
Authorization: Bearer TOKEN
Content-Type: application/json

{"expectedVersion":1,"mutationId":"device-operation-123","status":"eaten","actualEatingAt":"2026-11-09T18:07:00+02:00","confirmAnnouncedAmount":true}
```

Use a stable, unique `mutationId` when retrying the same update. The same mutation is
safe to resend; a different update with an old `expectedVersion` returns HTTP 409.
Only the owning patient can update a meal. Corrections retain prior medical values in
`meal_revisions`; general audit metadata contains only versions, transition, and the
mutation identifier.

Supplied numeric values accept finite nonnegative JSON numbers or plain decimal strings.
The documented legacy unit strings `45g` and `2 U` are accepted by their respective
fields. Booleans, blank strings, malformed strings, negatives, NaN, and infinity are
rejected. Omitted optional values become SQL `NULL`; explicit zero remains zero.

Profile form numbers use a deliberately narrower boundary rule: blank or whitespace-only
optional values (`age`, `weight`, `height`, `diagnosisYear`, and `yearsExperience`) clear
that value to SQL `NULL`, while zero remains zero and malformed, negative, boolean, or
nonfinite input is rejected. Omitting one of these properties during a profile update
preserves its stored value. Public account responses continue to represent unknown profile
numbers as empty strings for client compatibility. These profile-only rules do not apply
to glucose, carbohydrate, or insulin inputs, where blank values remain invalid.

Older rows that may have had consumption inferred solely from a legacy `carbs` field
are not rewritten automatically. Review them with a read-only query such as:

```sql
SELECT id, patient_id, announced_carbs_g, consumed_carbs_g, actual_eating_at, legacy_payload
FROM meals
WHERE status = 'eaten'
  AND legacy_payload ? 'carbs'
  AND confirmation_provenance = '{}'::jsonb;
```

Resolve each row from patient/source evidence through an audited correction workflow.
The JSON importer now keeps ambiguous real legacy meals planned with null consumption;
only the explicitly documented demo IDs use the fixed synthetic fixture date and amount.

## Access and conversation history

The current one-doctor workflow is preserved. Requesting a different doctor ends the former active assignment and conversation before creating the new pending assignment. Records are retained for history, but the snapshot API exposes messages only from the current active conversation. Therefore a newly assigned doctor cannot see a former doctor's conversation, and the former doctor loses snapshot access after reassignment. A future audited history endpoint can expose retained conversations under a separately approved policy.

## Compatibility and limitations

Existing `/api` response shapes are retained for the React and Flutter clients. Snapshots additionally return normalized meal status, planned/actual times, announced/consumed carbohydrates, and version; normalized columns override stale values in `legacy_payload`.

The existing admin screens still use frontend/demo state. This migration does not create an admin role, an admin provisioning API, or broad administrative access. New doctor accounts cannot be self-registered through `/api/auth/bridge`; they must be explicitly provisioned in a controlled process.

Client-provided IDs keep identical creates idempotent, while a conflicting create returns HTTP 409. Meal edits use optimistic versions and retry-safe mutation IDs; broader durable offline conflict resolution is not claimed.

## Client synchronization

The React client persists an explicit upload state with each locally created glucose,
meal, insulin, or message record. Snapshot records are server-authoritative and are never
implicitly added to the upload queue. Pending local records survive a browser reload and
are preserved while snapshots merge; successful uploads are acknowledged before a later
snapshot replaces the local copy. Only one request per record may be in flight. Temporary
failures use bounded backoff (at most five attempts), while HTTP 409 conflicts stop
automatic retry and remain visible for review.

The queue fields `syncState`, `syncAttempts`, `syncNextAttemptAt`, and `syncError`
are browser-local metadata. They are removed before an upload, never stored in new
`legacy_payload` values, and filtered from API responses for older rows that already
contain them. Clinical timestamps, recommendation links, and confirmation provenance
remain part of the clinical request and response.

Create idempotency compares normalized clinical values and timestamp instants rather than
raw legacy JSON. Thus `2026-01-01T13:10:00Z` and
`2026-01-01T13:10:00.000Z` are equivalent, while changed ownership, amounts, event times,
sender identity, or other authoritative values still conflict. The browser queue is
durable only in that browser's local storage; clearing site data removes unsynchronized
local entries, and there is no cross-device offline queue.

## Emergency contacts

Patient profile screens in React and the active Flutter app manage structured emergency
contacts through `/api/emergency-contacts`. Patients can add, edit, delete, and select one
primary contact. Phone numbers are text in international form, for example
`+201001234567`. Contacts are stored for reference; adding one does not send an alert or
place a call. These endpoints remain patient-only.

The older `patientProfile.emergencyContact` free-text value remains visible as legacy
information but is not editable alongside structured contacts, parsed automatically, or
deleted. The patient must explicitly create a structured contact after reviewing it.

Local verification from the repository root:

```bash
npm run test:api                 # requires dedicated TEST_DATABASE_URL
npm --workspace apps/web test
npm run test:web:integration     # simulated DOM + live API; requires TEST_DATABASE_URL with _test in its database name
npm run build:web
cd apps/mobile
flutter analyze lib/patient_app.dart lib/data/sync_api.dart
flutter test
```
