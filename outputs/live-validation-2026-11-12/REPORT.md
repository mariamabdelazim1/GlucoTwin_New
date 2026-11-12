# GlucoTwin Flutter offline-outbox validation

Date: 2026-11-12 (Africa/Cairo)

## Repository and environment

- Repository: `/Users/mariammohamed/Documents/uni/sem8/grad/GlucoTwin_New`
- Branch: `mariam`
- Commit: `e35cf17b619ed341e0d8133cd9b1c09cc0354ded` (`fixing app-db`)
- Initial working tree: clean. No source files were changed during this validation.
- Final working tree: only this untracked evidence directory was added.
- Flutter: 3.47.9 stable, framework `c197ca5199`
- Dart: 3.13.7
- Simulator: iPhone 18 Pro, iOS 27.2, UDID `C53258A4-9BDC-4081-BFC7-42373614375E`
- Dedicated database: `glucotwin_ui_test` on local PostgreSQL 16
- API: `http://127.0.0.1:8787`
- Accounts/data: seeded demo patient Omar Hassan and synthetic integration accounts only. No real patient data was used.

## Automated checks

### Outbox and widget tests

Command:

```sh
cd apps/mobile
flutter test test/offline_outbox_test.dart test/widget_test.dart
```

Result: PASS, 17 tests.

The 15 outbox tests cover persistence across `SyncApi` recreation, account isolation, lost-response acknowledgement, conflicts, meal dependencies/version reuse, concurrent queue writes, enqueue-during-upload preservation, same-account pending resume, blocked failed/conflict operations, retry-delay bypass, selected retry isolation, 401 stop/resume, and account switching during an in-flight upload. The two widget tests passed.

### Targeted analysis

Command:

```sh
cd apps/mobile
flutter analyze lib/data/sync_api.dart test/offline_outbox_test.dart test/widget_test.dart integration_test/live_offline_save_test.dart
```

Result: PASS, `No issues found!`

### Dedicated database preparation

Commands:

```sh
brew services start postgresql@16
TEST_DATABASE_URL=postgresql://mariammohamed@127.0.0.1:5432/glucotwin_ui_test npm --workspace services/api run db:migrate:test
TEST_DATABASE_URL=postgresql://mariammohamed@127.0.0.1:5432/glucotwin_ui_test npm --workspace services/api run db:seed:test
```

Result: PASS. Migrations were current and the test seed completed idempotently.

### Live Flutter offline integration test

API command used before and after the deliberate outage:

```sh
DATABASE_URL=postgresql://mariammohamed@127.0.0.1:5432/glucotwin_ui_test \
TEST_DATABASE_URL=postgresql://mariammohamed@127.0.0.1:5432/glucotwin_ui_test \
TOKEN_SECRET=offline-live-test-secret \
SYNC_HOST=127.0.0.1 SYNC_PORT=8787 \
npm --workspace services/api run dev
```

Test command:

```sh
cd apps/mobile
flutter test integration_test/live_offline_save_test.dart \
  -d C53258A4-9BDC-4081-BFC7-42373614375E \
  --dart-define=API_BASE_URL=http://127.0.0.1:8787
```

The API was stopped at the test's `OFFLINE_PHASE_READY` marker and restarted after `OFFLINE_QUEUED_READY`.

- First attempt: FAIL. The API was initially started with `TOKEN_SECRET=live-validation-secret`, while the simulator Keychain restored a synthetic session issued with the established test secret `offline-live-test-secret`. Uploads correctly received 401 and synchronization paused. This was a test-environment secret mismatch, not an application persistence defect.
- Corrected attempt, without source changes: PASS, 1 test in 1m38s.
- The corrected run queued glucose 223 mg/dL, insulin 3 U, and a planned/confirmed meal while the API was stopped; all synchronized after restart.
- Exact IDs from the corrected integration run each had one row after additional polling: glucose `ho38d8kb48`, insulin `ho38das07q`, meal `ho38dbhv0t`.

Evidence:

- [Integration queued](integration-queued-valid.png)
- [Integration synchronized](integration-synced-valid.png)

`integration-queued.png` is retained as evidence from the diagnosed secret-mismatch run and is not used as proof of a passing check.

### Diff validation

Command:

```sh
git diff --check
```

Result: PASS, no output.

## Real installed-app test through the UI

The normal debug application was installed once with:

```sh
cd apps/mobile
flutter run -d C53258A4-9BDC-4081-BFC7-42373614375E \
  --dart-define=API_BASE_URL=http://127.0.0.1:8787
```

Flutter was detached with `d`, leaving the installed app running. Xcode 27.2 Device Hub was used to interact through the real Flutter screens.

Verified through the UI:

1. Signed out, then signed in through the Patient sign-in screen using the seeded synthetic Omar Hassan account.
2. Stopped the test API and observed `Connection lost. Showing records saved securely on this device.`
3. Entered glucose 247 mg/dL. UI showed `Saved on this device; waiting to sync`.
4. Entered actual insulin 4 U at Lunch with 51 g carbohydrates and 147 mg/dL pre-meal glucose. UI showed it queued.
5. Created planned Lunch meal `hi relaunch lentils`, announced 53 g, then confirmed it eaten with 49 g actually consumed. UI showed it queued.
6. Verified the three records remained queued while the API was unavailable.

Pre-termination evidence:

- [Installed app before termination](installed-before-termination-offline.png)

## Same-install terminate/relaunch proof

The installed data container before termination was:

```text
/Users/mariammohamed/Library/Developer/CoreSimulator/Devices/C53258A4-9BDC-4081-BFC7-42373614375E/data/Containers/Data/Application/0DEACBB2-8700-47C4-ABA9-4B9107EB017F
```

Commands:

```sh
xcrun simctl terminate C53258A4-9BDC-4081-BFC7-42373614375E com.example.glucotwin
xcrun simctl launch C53258A4-9BDC-4081-BFC7-42373614375E com.example.glucotwin
xcrun simctl get_app_container C53258A4-9BDC-4081-BFC7-42373614375E com.example.glucotwin data
```

Result:

- The relaunch returned PID 8235.
- The container path after relaunch was exactly the same path shown above.
- No build, reinstall, uninstall, or data reset occurred between record creation and relaunch.
- The Omar Hassan patient session was restored while offline.
- Glucose 247, the eaten meal, and insulin 4 U were restored with queued status.

Post-relaunch evidence:

- [Installed app after relaunch, still offline](installed-after-relaunch-offline.png)

## Reconnection and idempotency

After restarting the API, a normal refresh respected pending retry backoff. Signing out and signing back into the same account exercised the intended forced-pending resume path. All three records changed to `Synced` in the UI. Three further Refresh cycles completed with all records still synced.

- [Installed app after synchronization](installed-after-sync.png)

Database query:

```sql
SELECT 'glucose' AS kind,id,COUNT(*) AS rows,MIN(measured_at) AS event_at,
       MAX(glucose_mg_dl)::text AS value
FROM glucose_readings WHERE id='ho3gd8u4g0' GROUP BY id
UNION ALL
SELECT 'insulin',id,COUNT(*),MIN(administered_at),MAX(administered_units)::text
FROM insulin_doses WHERE id='ho3gdmck5o' GROUP BY id
UNION ALL
SELECT 'meal',id,COUNT(*),MIN(planned_eating_at),MAX(announced_carbs_g)::text
FROM meals WHERE id='ho3ge0myof' GROUP BY id;
```

Result after the additional refreshes:

| kind | stable ID | rows | original event timestamp | value |
|---|---|---:|---|---:|
| glucose | `ho3gd8u4g0` | 1 | `2026-11-12 17:17:03.054+02` | 247 mg/dL |
| insulin | `ho3gdmck5o` | 1 | `2026-11-12 17:17:25.749+02` | 4 U |
| meal | `ho3ge0myof` | 1 | `2026-11-12 17:17:49.749+02` | 53 g announced |

Meal lifecycle query:

```sql
SELECT id,status,announced_carbs_g,consumed_carbs_g,
       planned_eating_at,actual_eating_at,version,confirmation_provenance
FROM meals WHERE id='ho3ge0myof';
```

Result:

```text
id=ho3ge0myof
status=eaten
announced_carbs_g=53
consumed_carbs_g=49
planned_eating_at=2026-11-12 17:17:49.749+02
actual_eating_at=2026-11-12 17:17:53.749+02
version=2
confirmation source=patient_entered_actual
```

`meal_revisions` contained exactly one row for this meal, from version 1 to version 2.

The PostgreSQL `created_at` values were later than the original event timestamps, confirming that the offline event timestamps—not upload time—were preserved.

## Retry-safeguard coverage

Automated deterministic coverage (not simulated as UI conflicts):

- Same-account login resumes eligible pending operations but leaves failed/conflict operations blocked.
- Bypassing retry delay applies only to eligible pending operations.
- Explicit retry sends only the selected operation and preserves its meal version.
- A blocked meal creation keeps its dependent confirmation blocked.
- A 401 stops the worker immediately; same-account login resumes it.
- Account switching during an in-flight request preserves ownership and token isolation.

Real UI coverage:

- Offline records survived a true terminate/relaunch of the same installed app and container.
- Same-account login resumed the real pending queue after reconnect.
- Three repeated refreshes did not duplicate any stable ID.

## Fixes and limitations

- No application defect was found in this validation, so no source code was changed.
- The one live-test failure was caused by inconsistent test API token secrets. Rerunning with the established test secret passed without code changes.
- Failed/conflict injection, 401 sequencing, and in-flight account switching were verified by deterministic automated tests, not by manually corrupting the installed app's real queue through the UI.
- API unavailability was produced by stopping the local test API, not by changing the simulator's system network settings.
- The installed app remains installed with synthetic test data. Temporary API and PostgreSQL services are stopped after this report is finalized; the evidence files are retained.
