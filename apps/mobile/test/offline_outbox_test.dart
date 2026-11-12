import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:glucotwin/data/sync_api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

class MemoryStore implements KeyValueStore {
  final values = <String, String>{};
  @override
  Future<void> delete(String key) async => values.remove(key);
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async => values[key] = value;
}

Map<String, dynamic> account(String id) => {
      'id': id,
      'role': 'patient',
      'email': '$id@example.test',
      'patientProfile': {'fullName': 'Offline $id'},
    };

Future<void> seedSession(MemoryStore store, String id,
    {bool token = false}) async {
  store.values['glucotwin.session.account.v1'] = jsonEncode(account(id));
  if (token) store.values['glucotwin.session.token.v1'] = 'synthetic-token';
}

List<Map<String, dynamic>> storedOutbox(MemoryStore store, String id) =>
    ((jsonDecode(store.values['glucotwin.outbox.v1.$id'] ?? '[]') as List))
        .map((value) => Map<String, dynamic>.from(value as Map))
        .toList();

http.Response snapshotResponse(String patientId,
        {List<Map<String, dynamic>> glucose = const [],
        List<Map<String, dynamic>> bolus = const [],
        List<Map<String, dynamic>> food = const []}) =>
    http.Response(
        jsonEncode({
          'account': account(patientId),
          'glucose': glucose,
          'bolus': bolus,
          'food': food,
        }),
        200,
        headers: {'content-type': 'application/json'});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('pending record survives a new SyncApi instance with stable content',
      () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a');
    final first = SyncApi(store: store);
    await first.restore();
    const recordedAt = '2026-11-12T08:00:00.000Z';
    await first.queueAdd('glucose', {
      'id': 'stable-reading',
      'patientSlug': 'patient-a',
      'value': 0,
      'recordedAt': recordedAt,
      'time': '10:00 AM',
    });

    final relaunched = SyncApi(store: store);
    await relaunched.restore();
    final row =
        ((await relaunched.localSnapshot())['glucose'] as List).single as Map;
    expect(row['id'], 'stable-reading');
    expect(row['value'], 0);
    expect(row['recordedAt'], recordedAt);
    expect(row['syncState'], 'pending');
  });

  test('outbox is isolated from a different signed-in account', () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a');
    final first = SyncApi(store: store);
    await first.restore();
    await first.queueAdd('glucose', {
      'id': 'only-a',
      'patientSlug': 'patient-a',
      'value': 120,
      'recordedAt': '2026-11-12T08:00:00Z'
    });

    await seedSession(store, 'patient-b');
    final second = SyncApi(store: store);
    await second.restore();
    expect((await second.localSnapshot())['glucose'], isEmpty);
    expect(
        () => second.queueAdd('glucose', {
              'id': 'wrong-owner',
              'patientSlug': 'patient-a',
              'value': 121,
              'recordedAt': '2026-11-12T08:01:00Z'
            }),
        throwsA(isA<ApiException>()));
  });

  test('lost response is acknowledged only after matching snapshot content',
      () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a');
    var posts = 0;
    final client = MockClient((request) async {
      if (request.method == 'POST') {
        posts++;
        throw http.ClientException('response lost');
      }
      return http.Response(
          jsonEncode({
            'account': account('patient-a'),
            'glucose': [
              {
                'id': 'lost-response',
                'value': 123,
                'recordedAt': '2026-11-12T08:00:00.000Z'
              }
            ],
            'bolus': [],
            'food': []
          }),
          200,
          headers: {'content-type': 'application/json'});
    });
    final api = SyncApi(store: store, client: client);
    await api.restore();
    await api.queueAdd('glucose', {
      'id': 'lost-response',
      'patientSlug': 'patient-a',
      'value': 123,
      'recordedAt': '2026-11-12T10:00:00+02:00'
    });
    await api.saveToken('synthetic-token');
    await api.syncOutbox(force: true);
    expect(posts, 1);
    final row = ((await api.localSnapshot())['glucose'] as List).single as Map;
    expect(row['syncState'], 'synced');
    expect(jsonDecode(store.values['glucotwin.outbox.v1.patient-a']!) as List,
        isEmpty);
  });

  test('different content on 409 remains a visible conflict', () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a');
    final client = MockClient((request) async {
      if (request.method == 'POST') {
        return http.Response(jsonEncode({'error': 'Conflict'}), 409);
      }
      return http.Response(
          jsonEncode({
            'account': account('patient-a'),
            'glucose': [
              {
                'id': 'conflict-reading',
                'value': 999,
                'recordedAt': '2026-11-12T08:00:00Z'
              }
            ],
            'bolus': [],
            'food': []
          }),
          200);
    });
    final api = SyncApi(store: store, client: client);
    await api.restore();
    await api.queueAdd('glucose', {
      'id': 'conflict-reading',
      'patientSlug': 'patient-a',
      'value': 120,
      'recordedAt': '2026-11-12T08:00:00Z'
    });
    await api.saveToken('synthetic-token');
    await api.syncOutbox(force: true);
    final rows = ((await api.localSnapshot())['glucose'] as List).cast<Map>();
    expect(rows.singleWhere((row) => row['value'] == 120)['syncState'],
        'conflict');
  });

  test('meal update waits for create and reuses server version', () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a');
    var mealStatus = 'planned';
    var version = 1;
    final methods = <String>[];
    final client = MockClient((request) async {
      methods.add(request.method);
      if (request.method == 'POST') return http.Response('{}', 200);
      if (request.method == 'PATCH') {
        final body = jsonDecode(request.body) as Map;
        expect(body['expectedVersion'], 1);
        expect(body['mutationId'], 'stable-mutation');
        mealStatus = 'eaten';
        version = 2;
        return http.Response(jsonEncode({'meal': {}}), 200);
      }
      return http.Response(
          jsonEncode({
            'account': account('patient-a'),
            'glucose': [],
            'bolus': [],
            'food': [
              {
                'id': 'meal-1',
                'meal': 'Lunch',
                'items': 'Rice',
                'carbs': '40g',
                'announcedCarbsG': 40,
                'consumedCarbsG': mealStatus == 'eaten' ? 35 : null,
                'status': mealStatus,
                'plannedEatingAt': '2026-11-12T12:00:00Z',
                'actualEatingAt':
                    mealStatus == 'eaten' ? '2026-11-12T12:30:00Z' : null,
                'version': version,
              }
            ]
          }),
          200);
    });
    final api = SyncApi(store: store, client: client);
    await api.restore();
    await api.queueAdd('food', {
      'id': 'meal-1',
      'patientSlug': 'patient-a',
      'meal': 'Lunch',
      'items': 'Rice',
      'carbs': '40g',
      'status': 'planned',
      'plannedEatingAt': '2026-11-12T12:00:00Z'
    });
    await api.queueMealUpdate('meal-1', {
      'expectedVersion': null,
      'mutationId': 'stable-mutation',
      'status': 'eaten',
      'actualEatingAt': '2026-11-12T12:30:00Z',
      'consumedCarbsG': 35
    });
    await api.saveToken('synthetic-token');
    await api.syncOutbox(force: true);
    expect(methods.where((value) => value == 'POST').length, 1);
    expect(methods.where((value) => value == 'PATCH').length, 1);
    final row = ((await api.localSnapshot())['food'] as List).single as Map;
    expect(row['status'], 'eaten');
    expect(row['consumedCarbsG'], 35);
    expect(row['syncState'], 'synced');
  });

  test('enqueue during a pending upload cannot be overwritten', () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a', token: true);
    final firstStarted = Completer<void>();
    final releaseFirst = Completer<void>();
    final secondStarted = Completer<void>();
    final releaseSecond = Completer<void>();
    final secondSnapshot = Completer<void>();
    final uploadedIds = <String>[];
    var snapshots = 0;
    final client = MockClient((request) async {
      if (request.method == 'POST') {
        final id = (jsonDecode(request.body) as Map)['id'] as String;
        uploadedIds.add(id);
        if (id == 'first-reading') {
          firstStarted.complete();
          await releaseFirst.future;
        } else {
          secondStarted.complete();
          await releaseSecond.future;
        }
        return http.Response('{}', 200);
      }
      snapshots++;
      if (snapshots == 2) secondSnapshot.complete();
      return snapshotResponse('patient-a');
    });
    final api = SyncApi(store: store, client: client);
    await api.restore();

    await api.queueAdd('glucose', {
      'id': 'first-reading',
      'patientSlug': 'patient-a',
      'value': 111,
      'recordedAt': '2026-11-12T08:00:00Z',
    });
    await firstStarted.future;
    await api.queueAdd('glucose', {
      'id': 'second-reading',
      'patientSlug': 'patient-a',
      'value': 112,
      'recordedAt': '2026-11-12T08:01:00Z',
    });
    expect(storedOutbox(store, 'patient-a').map((value) => value['recordId']),
        containsAll(['first-reading', 'second-reading']));

    releaseFirst.complete();
    await secondStarted.future;
    expect(
        storedOutbox(store, 'patient-a').single['recordId'], 'second-reading');
    releaseSecond.complete();
    await secondSnapshot.future;
    expect(uploadedIds, ['first-reading', 'second-reading']);
    expect(storedOutbox(store, 'patient-a'), isEmpty);
  });

  test('meal confirmation queued during create survives and follows create',
      () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a', token: true);
    final createStarted = Completer<void>();
    final releaseCreate = Completer<void>();
    final updateStarted = Completer<void>();
    final releaseUpdate = Completer<void>();
    final finalSnapshot = Completer<void>();
    var created = false;
    var updated = false;
    final methods = <String>[];
    final client = MockClient((request) async {
      if (request.method == 'POST') {
        methods.add('create');
        createStarted.complete();
        await releaseCreate.future;
        created = true;
        return http.Response('{}', 200);
      }
      if (request.method == 'PATCH') {
        methods.add('update');
        final body = jsonDecode(request.body) as Map;
        expect(created, isTrue);
        expect(body['expectedVersion'], 1);
        expect(body['mutationId'], 'confirm-while-creating');
        updateStarted.complete();
        await releaseUpdate.future;
        updated = true;
        return http.Response(jsonEncode({'meal': {}}), 200);
      }
      if (updated) finalSnapshot.complete();
      return snapshotResponse('patient-a',
          food: created
              ? [
                  {
                    'id': 'pending-meal',
                    'meal': 'Lunch',
                    'items': 'Rice',
                    'carbs': '40g',
                    'announcedCarbsG': 40,
                    'consumedCarbsG': updated ? 35 : null,
                    'status': updated ? 'eaten' : 'planned',
                    'plannedEatingAt': '2026-11-12T12:00:00Z',
                    'actualEatingAt': updated ? '2026-11-12T12:30:00Z' : null,
                    'version': updated ? 2 : 1,
                  }
                ]
              : []);
    });
    final api = SyncApi(store: store, client: client);
    await api.restore();
    await api.queueAdd('food', {
      'id': 'pending-meal',
      'patientSlug': 'patient-a',
      'meal': 'Lunch',
      'items': 'Rice',
      'carbs': '40g',
      'status': 'planned',
      'plannedEatingAt': '2026-11-12T12:00:00Z',
    });
    await createStarted.future;
    await api.queueMealUpdate('pending-meal', {
      'expectedVersion': null,
      'mutationId': 'confirm-while-creating',
      'status': 'eaten',
      'actualEatingAt': '2026-11-12T12:30:00Z',
      'consumedCarbsG': 35,
    });
    final queued = storedOutbox(store, 'patient-a');
    expect(
        queued.singleWhere((value) =>
            value['operationId'] == 'confirm-while-creating')['dependsOn'],
        'op-pending-meal');

    releaseCreate.complete();
    await updateStarted.future;
    expect(methods, ['create', 'update']);
    expect(storedOutbox(store, 'patient-a').single['operationId'],
        'confirm-while-creating');
    releaseUpdate.complete();
    await finalSnapshot.future;
    expect(storedOutbox(store, 'patient-a'), isEmpty);
  });

  test('concurrent queue writes preserve both records', () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a');
    final api = SyncApi(store: store);
    await api.restore();
    await Future.wait([
      api.queueAdd('glucose', {
        'id': 'concurrent-one',
        'patientSlug': 'patient-a',
        'value': 101,
        'recordedAt': '2026-11-12T09:00:00Z',
      }),
      api.queueAdd('glucose', {
        'id': 'concurrent-two',
        'patientSlug': 'patient-a',
        'value': 102,
        'recordedAt': '2026-11-12T09:01:00Z',
      }),
    ]);
    expect(storedOutbox(store, 'patient-a').map((value) => value['recordId']),
        containsAll(['concurrent-one', 'concurrent-two']));
  });

  test('recreated API preserves IDs payloads timestamps and dependencies',
      () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a');
    final first = SyncApi(store: store);
    await first.restore();
    await Future.wait([
      first.queueAdd('glucose', {
        'id': 'durable-glucose',
        'patientSlug': 'patient-a',
        'value': 0,
        'recordedAt': '2026-11-12T10:00:00Z',
      }),
      first.queueAdd('food', {
        'id': 'durable-meal',
        'patientSlug': 'patient-a',
        'meal': 'Lunch',
        'items': 'Soup',
        'carbs': '0g',
        'status': 'planned',
        'plannedEatingAt': '2026-11-12T12:00:00Z',
      }),
    ]);
    await first.queueMealUpdate('durable-meal', {
      'expectedVersion': null,
      'mutationId': 'durable-confirm',
      'status': 'eaten',
      'actualEatingAt': '2026-11-12T12:30:00Z',
      'consumedCarbsG': 0,
    });
    final before = storedOutbox(store, 'patient-a');

    final restored = SyncApi(store: store);
    await restored.restore();
    final after = storedOutbox(store, 'patient-a');
    expect(after, before);
    expect(
        after.singleWhere(
            (value) => value['operationId'] == 'durable-confirm')['dependsOn'],
        'op-durable-meal');
    expect(
        after.singleWhere(
                (value) => value['recordId'] == 'durable-glucose')['payload']
            ['value'],
        0);
  });

  test('401 stops the worker and successful same-account login resumes it',
      () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a');
    var clinicalRequests = 0;
    var resumedRequests = 0;
    final resumed = Completer<void>();
    final finalSnapshot = Completer<void>();
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/auth/login')) {
        return http.Response(
            jsonEncode({
              'token': 'renewed-token',
              'account': account('patient-a'),
            }),
            200);
      }
      if (request.method == 'POST') {
        clinicalRequests++;
        if (clinicalRequests == 1) {
          return http.Response(jsonEncode({'error': 'Expired'}), 401);
        }
        expect(request.headers['authorization'], 'Bearer renewed-token');
        resumedRequests++;
        if (resumedRequests == 2) resumed.complete();
        return http.Response('{}', 200);
      }
      if (resumedRequests == 2 && !finalSnapshot.isCompleted) {
        finalSnapshot.complete();
      }
      return snapshotResponse('patient-a');
    });
    final api = SyncApi(store: store, client: client);
    await api.restore();
    await Future.wait([
      api.queueAdd('glucose', {
        'id': 'auth-one',
        'patientSlug': 'patient-a',
        'value': 131,
        'recordedAt': '2026-11-12T11:00:00Z',
      }),
      api.queueAdd('glucose', {
        'id': 'auth-two',
        'patientSlug': 'patient-a',
        'value': 132,
        'recordedAt': '2026-11-12T11:01:00Z',
      }),
    ]);
    await api.saveToken('expired-token');
    await api.syncOutbox(force: true);
    expect(clinicalRequests, 1);
    final paused = storedOutbox(store, 'patient-a');
    expect(paused, hasLength(2));
    expect(paused.map((value) => value['recordId']),
        containsAll(['auth-one', 'auth-two']));
    expect(paused.first['payload']['value'], 131);

    await api.syncOutbox(force: true);
    expect(clinicalRequests, 1);

    await api.login('patient-a@example.test', 'password');
    await resumed.future;
    await finalSnapshot.future;
    expect(clinicalRequests, 3);
    expect(storedOutbox(store, 'patient-a'), isEmpty);
  });

  test('account switch during upload preserves ownership and token isolation',
      () async {
    final store = MemoryStore();
    await seedSession(store, 'patient-a', token: true);
    final aStarted = Completer<void>();
    final releaseA = Completer<void>();
    final bUploaded = Completer<void>();
    final bSnapshot = Completer<void>();
    final uploads = <String, String?>{};
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/auth/login')) {
        return http.Response(
            jsonEncode({
              'token': 'patient-b-token',
              'account': account('patient-b'),
            }),
            200);
      }
      if (request.method == 'POST') {
        final id = (jsonDecode(request.body) as Map)['id'] as String;
        uploads[id] = request.headers['authorization'];
        if (id == 'patient-a-reading') {
          aStarted.complete();
          await releaseA.future;
        } else {
          bUploaded.complete();
        }
        return http.Response('{}', 200);
      }
      if (uploads.containsKey('patient-b-reading')) bSnapshot.complete();
      return snapshotResponse('patient-b');
    });
    final api = SyncApi(store: store, client: client);
    await api.restore();
    await api.queueAdd('glucose', {
      'id': 'patient-a-reading',
      'patientSlug': 'patient-a',
      'value': 141,
      'recordedAt': '2026-11-12T12:00:00Z',
    });
    await aStarted.future;
    await api.signOut();
    await api.login('patient-b@example.test', 'password');
    await api.queueAdd('glucose', {
      'id': 'patient-b-reading',
      'patientSlug': 'patient-b',
      'value': 142,
      'recordedAt': '2026-11-12T12:01:00Z',
    });
    releaseA.complete();
    await bUploaded.future;
    await bSnapshot.future;

    expect(uploads['patient-a-reading'], 'Bearer synthetic-token');
    expect(uploads['patient-b-reading'], 'Bearer patient-b-token');
    final aQueue = storedOutbox(store, 'patient-a');
    expect(aQueue, hasLength(1));
    expect(aQueue.single['recordId'], 'patient-a-reading');
    expect(aQueue.single['state'], 'pending');
    expect(storedOutbox(store, 'patient-b'), isEmpty);
    expect(api.currentPatientId, 'patient-b');
    expect((await api.localSnapshot())['glucose'], isEmpty);
  });
}
