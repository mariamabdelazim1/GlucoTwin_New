# GlucoTwin patient mobile app

## Offline clinical logging

The active patient app keeps glucose readings, administered insulin doses, meal
creates, and meal confirmations/cancellations in an account-scoped durable
outbox. The session token, minimum cached account/snapshot, and each account's
outbox are stored with `flutter_secure_storage` (iOS Keychain and Android
EncryptedSharedPreferences). Chat, doctor requests, contacts, and other care
operations remain online-only.

The form creates the record ID and event timestamp once and persists the
operation before closing. Records retain those values across retries. The UI
distinguishes:

- **Saved on this device; waiting to sync**: durable locally, not yet confirmed
  by the server and therefore not promised as doctor-visible.
- **Syncing**: one worker is attempting the operation.
- **Synced**: confirmed by an HTTP success or a snapshot with matching clinical
  content.
- **Needs attention**: permanent validation failure or a genuine content/version
  conflict; the record remains available for review and manual retry.

Transient failures use bounded exponential backoff and retry during polling,
manual refresh, and app resume. An interrupted `syncing` operation becomes
`pending` at the next launch. A lost response is acknowledged only when a fresh
snapshot matches the record ID and authoritative clinical content. HTTP 401
pauses uploads without deleting the session cache or outbox.

Outbox read-modify-write operations are serialized per account. The storage
lock is released while HTTP is in flight, so a patient can keep saving records;
completion handling reloads the latest queue and changes only the attempted
operation. Uploads retain their owning session token. A 401 stops the worker
immediately, and logout or account switching prevents an older response from
changing the new account's queue, cache, or snapshot.

Meal updates retain a stable `mutationId` and expected version. An offline
confirmation/cancellation waits for its planned-meal create to be confirmed.
Stale server versions remain visible as conflicts; the client does not silently
overwrite them. Confirmation records the actual consumed carbohydrates, which
may differ from the announced amount. Cancellation leaves consumption and the
actual eating time unknown.

Signing out removes the active credential/account pointer but deliberately
retains encrypted per-account cached data and pending operations. A different
account cannot see or upload that queue. Signing back into the owning account
resumes it.

Current limitation: conflict resolution is retry/review only; there is no field-
level conflict editor. Secure-storage JSON is appropriate for the expected small
clinical outbox, but a future high-volume sensor queue should use an encrypted
database instead.

## Run

From the repository root, start the isolated API, then run the iOS app:

```sh
npm run dev:api
cd apps/mobile
flutter run -d <simulator-id> --dart-define=API_BASE_URL=http://127.0.0.1:8787
```

Use `http://10.0.2.2:8787` for the Android emulator. For a physical device, bind
the API to `0.0.0.0` and use the computer's LAN address.

## Reproducible checks

```sh
cd apps/mobile
flutter test test/offline_outbox_test.dart
flutter test
flutter analyze lib/data/sync_api.dart lib/patient_app.dart test/offline_outbox_test.dart

# With the dedicated PostgreSQL test API running, stop it at OFFLINE_PHASE_READY.
flutter test integration_test/live_offline_save_test.dart \
  -d <simulator-id> \
  --dart-define=API_BASE_URL=http://127.0.0.1:8787
```

For a real session-restoration check, install/run the app once, then use
`xcrun simctl terminate <device-id> <bundle-id>` followed by
`xcrun simctl launch <device-id> <bundle-id>`. Do not use `flutter test` as the
relaunch step because it reinstalls the test bundle and does not prove durable
restoration.
