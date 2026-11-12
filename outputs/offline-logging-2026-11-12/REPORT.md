# GlucoTwin durable offline logging report

Date: 2026-11-12  
Branch: `mariam`  
Starting/reviewed HEAD: `9c79a2993339e28a41e0f2944cbd8e2a1002ce6c`  
No commit, push, deployment, Python model, physiology, checkpoint, or bolus-optimization change was made.

## Implementation

- Added an encrypted, account-scoped outbox using `flutter_secure_storage`
  (iOS Keychain / Android EncryptedSharedPreferences).
- Cached the minimum account and server snapshot needed for offline viewing and
  logging. A network error no longer signs the patient out.
- Persisted stable operation IDs, record IDs, event times, clinical payloads,
  retry counts, next-attempt times, state, dependency, and error classification.
- Added a single-worker guard, interrupted-sync recovery, bounded exponential
  backoff, app-resume/poll/manual retry triggers, authentication pause, permanent
  validation failure, and explicit conflict state.
- Lost responses are reconciled only against a snapshot with matching stable ID
  and authoritative clinical content.
- Added offline glucose, actual administered insulin, meal create, meal
  confirmation with actual carbohydrates, and meal cancellation support.
- Meal updates retain a stable mutation ID and wait for their create operation;
  the server version is filled only after the planned meal is authoritative.
- Added visible pending, syncing, synced, and needs-attention states. Pending
  records explicitly say they are saved on the device and are not claimed as
  doctor-visible.
- Kept chat, doctor requests, contacts, and other care actions online-only.
- Replaced dialog-local controllers with stateful dialog widgets that dispose
  controllers after their route lifecycle. Save is disabled while durable local
  persistence is in progress, preventing repeated taps.

## Real iOS simulator evidence

Device: iPhone 18 Pro, iOS 27.2 (`C53258A4-9BDC-4081-BFC7-42373614375E`).  
Database: dedicated synthetic `glucotwin_ui_test`.  
API: stopped after `OFFLINE_PHASE_READY`, restarted after
`OFFLINE_QUEUED_READY`.

The Flutter form created:

- glucose: 223 mg/dL;
- actual administered insulin: 3 U, with 45 g carbohydrates and 140 mg/dL
  pre-meal glucose;
- planned “Offline rice” meal: 40 g announced, later explicitly confirmed as
  eaten with 35 g actually consumed while still offline.

`queued-offline-all-records.png` shows the meal and bolus retained with “Saved
on this device; waiting to sync.” `synchronized-all-records.png` shows the same
records as “Synced” after the API restarted.

Before restart, `database-before-all-sync.txt` contained `offline_rice=0` and
the new run had not added its latest IDs. After restart,
`database-after-all-sync.tsv` shows the new stable IDs:

- glucose `ho2s4r3i4t`, one row;
- insulin `ho2s4tb23z`, one row;
- meal `ho2s4ufwl1`, one row, 35 g consumed.

Every displayed stable ID has `rows_for_id=1`. Earlier rows in the evidence are
separate synthetic test attempts with different IDs, not duplicates.

## Checks run

- `flutter test`: **7 passed**.
- Focused Flutter analyzer: **0 errors/warnings**, 32 existing/style `info`
  findings for optional braces.
- iOS simulator debug build: **passed** after installing CocoaPods.
- Live Flutter offline/reconnect integration test: **passed**, 1 test, 1m43s.
- PostgreSQL API suite: **10 passed**.
- Web synchronization unit suite: **11 passed**.
- Web journey suite: **3 passed**.
- React/PostgreSQL synchronization integration: **1 passed**.
- React production build: **passed**; Vite reported only its existing large-
  chunk advisory.
- `git diff --check`: **passed**.

The live test initially exposed two scrolling-test issues while it was expanded
to insulin and meals. Those attempts failed before final assertions; the final
unchanged test run passed end-to-end. They did not touch non-test data.

## Limitations

- The Flutter integration harness removes its installed test bundle on exit, so
  it cannot itself prove a non-destructive terminate/relaunch. A new `SyncApi`
  instance restoring the same protected store is covered by an automated test,
  and the iOS Keychain session survived successive test-bundle installations,
  but an exact `simctl terminate` + `simctl launch` assertion was not completed.
- The doctor web application was covered by its React/PostgreSQL integration and
  the records are authoritative in PostgreSQL, but a new browser screenshot of
  these exact three record IDs was not captured because the Mac UI surface was
  locked.
- Lost response, account isolation, stable timestamp/content restoration,
  dependency ordering, and real conflicts are deterministic automated tests;
  conflict and account-switch screens were not separately exercised in the
  final live simulator run.
- Conflict handling currently offers review/retry, not a field-level merge
  editor.
- Secure-storage JSON is intended for the expected small manual clinical
  outbox. A future high-volume CGM queue should use an encrypted database.
