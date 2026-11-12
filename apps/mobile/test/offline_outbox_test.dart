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
      if (request.method == 'POST')
        return http.Response(jsonEncode({'error': 'Conflict'}), 409);
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
}
