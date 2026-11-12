import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

typedef JsonMap = Map<String, dynamic>;

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode, this.network = false});
  final String message;
  final int? statusCode;
  final bool network;
  @override
  String toString() => message;
}

abstract class KeyValueStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class ProtectedStore implements KeyValueStore {
  const ProtectedStore();
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(
        accessibility: KeychainAccessibility.first_unlock_this_device),
  );
  @override
  Future<String?> read(String key) => _storage.read(key: key);
  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);
  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class OutboxOperation {
  OutboxOperation(
      {required this.operationId,
      required this.recordId,
      required this.patientId,
      required this.type,
      required this.payload,
      required this.eventAt,
      required this.createdAt,
      this.state = 'pending',
      this.attempts = 0,
      this.nextAttemptAt,
      this.errorKind,
      this.errorMessage,
      this.dependsOn});
  final String operationId;
  final String recordId;
  final String patientId;
  final String type;
  final JsonMap payload;
  final String eventAt;
  final String createdAt;
  String state;
  int attempts;
  String? nextAttemptAt;
  String? errorKind;
  String? errorMessage;
  final String? dependsOn;

  factory OutboxOperation.fromJson(JsonMap value) => OutboxOperation(
      operationId: value['operationId'] as String,
      recordId: value['recordId'] as String,
      patientId: value['patientId'] as String,
      type: value['type'] as String,
      payload: Map<String, dynamic>.from(value['payload'] as Map),
      eventAt: value['eventAt'] as String,
      createdAt: value['createdAt'] as String,
      state: value['state'] as String? ?? 'pending',
      attempts: value['attempts'] as int? ?? 0,
      nextAttemptAt: value['nextAttemptAt'] as String?,
      errorKind: value['errorKind'] as String?,
      errorMessage: value['errorMessage'] as String?,
      dependsOn: value['dependsOn'] as String?);
  JsonMap toJson() => {
        'operationId': operationId,
        'recordId': recordId,
        'patientId': patientId,
        'type': type,
        'payload': payload,
        'eventAt': eventAt,
        'createdAt': createdAt,
        'state': state,
        'attempts': attempts,
        'nextAttemptAt': nextAttemptAt,
        'errorKind': errorKind,
        'errorMessage': errorMessage,
        'dependsOn': dependsOn
      };
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}

class SyncApi {
  SyncApi({KeyValueStore? store, http.Client? client})
      : store = store ?? const ProtectedStore(),
        _client = client ?? http.Client();
  static const configuredBaseUrl = String.fromEnvironment('API_BASE_URL');
  static String get baseUrl => configuredBaseUrl.isNotEmpty
      ? configuredBaseUrl
      : kIsWeb
          ? 'http://127.0.0.1:8787'
          : 'http://10.0.2.2:8787';
  static const _tokenKey = 'glucotwin.session.token.v1';
  static const _accountKey = 'glucotwin.session.account.v1';
  final KeyValueStore store;
  final http.Client _client;
  String? token;
  String? currentPatientId;
  JsonMap? cachedAccount;
  JsonMap _serverSnapshot = {};
  bool authPaused = false;
  bool _syncing = false;
  int _sessionRevision = 0;
  final Map<String, Future<void>> _outboxLocks = {};
  VoidCallback? onLocalChange;
  String _snapshotKey(String id) => 'glucotwin.snapshot.v1.$id';
  String _outboxKey(String id) => 'glucotwin.outbox.v1.$id';

  Future<T> _withOutboxLock<T>(String id, Future<T> Function() action) async {
    final previous = _outboxLocks[id] ?? Future<void>.value();
    final released = Completer<void>();
    final queued = previous.catchError((_) {}).then((_) => released.future);
    _outboxLocks[id] = queued;
    await previous.catchError((_) {});
    try {
      return await action();
    } finally {
      released.complete();
      if (identical(_outboxLocks[id], queued)) _outboxLocks.remove(id);
    }
  }

  Future<void> restore() async {
    final restoringRevision = ++_sessionRevision;
    final restoredToken = await store.read(_tokenKey);
    final saved = await store.read(_accountKey);
    if (restoringRevision != _sessionRevision) return;
    token = restoredToken;
    if (saved != null) {
      cachedAccount = Map<String, dynamic>.from(jsonDecode(saved) as Map);
      currentPatientId = cachedAccount?['id'] as String?;
    }
    if (token == null) {
      final preferences = await SharedPreferences.getInstance();
      final legacy = preferences.getString('patient_sync_token');
      if (legacy != null) {
        await store.write(_tokenKey, legacy);
        if (restoringRevision != _sessionRevision) return;
        token = legacy;
        authPaused = false;
        await preferences.remove('patient_sync_token');
      }
    }
    if (currentPatientId != null) {
      final id = currentPatientId!;
      final raw = await store.read(_snapshotKey(id));
      if (restoringRevision != _sessionRevision || currentPatientId != id) return;
      if (raw != null)
        _serverSnapshot = Map<String, dynamic>.from(jsonDecode(raw) as Map);
      await _withOutboxLock(id, () async {
        final operations = await _readOutboxUnlocked(id);
        for (final op in operations.where((value) => value.state == 'syncing')) {
          op.state = 'pending';
          op.nextAttemptAt = null;
        }
        await _writeOutboxUnlocked(id, operations);
      });
    }
  }

  Future<void> saveToken(String value) async {
    _sessionRevision++;
    token = value;
    authPaused = false;
    await store.write(_tokenKey, value);
  }

  Future<void> _saveAccount(JsonMap account) async {
    cachedAccount = Map<String, dynamic>.from(account);
    currentPatientId = account['id'] as String;
    await store.write(_accountKey, jsonEncode(account));
  }

  Future<void> signOut() async {
    _sessionRevision++;
    token = null;
    currentPatientId = null;
    cachedAccount = null;
    _serverSnapshot = {};
    authPaused = false;
    await store.delete(_tokenKey);
    await store.delete(_accountKey);
  }

  Future<JsonMap> request(String path,
      {String method = 'GET', JsonMap? data, String? bearerToken}) async {
    try {
      final request = http.Request(method, Uri.parse('$baseUrl/api/$path'));
      request.headers['Content-Type'] = 'application/json';
      final requestToken = bearerToken ?? token;
      if (requestToken != null)
        request.headers['Authorization'] = 'Bearer $requestToken';
      if (data != null) request.body = jsonEncode(data);
      final streamed =
          await _client.send(request).timeout(const Duration(seconds: 12));
      final response = await http.Response.fromStream(streamed);
      JsonMap result = {};
      if (response.body.trim().isNotEmpty) {
        final decoded = jsonDecode(response.body);
        if (decoded is Map) result = Map<String, dynamic>.from(decoded);
      }
      if (response.statusCode >= 400)
        throw ApiException('${result['error'] ?? 'Sync request failed'}',
            statusCode: response.statusCode);
      return result;
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw ApiException('The sync service did not respond.', network: true);
    } catch (_) {
      throw ApiException('Cannot reach the sync service.', network: true);
    }
  }

  Future<JsonMap> login(String email, String password) async {
    final result = await request('auth/login',
        method: 'POST', data: {'email': email, 'password': password});
    await saveToken(result['token'] as String);
    final account = Map<String, dynamic>.from(result['account'] as Map);
    await _saveAccount(account);
    final raw = await store.read(_snapshotKey(currentPatientId!));
    _serverSnapshot =
        raw == null ? {} : Map<String, dynamic>.from(jsonDecode(raw) as Map);
    unawaited(syncOutbox(force: true));
    return account;
  }

  Future<JsonMap> register(JsonMap account) async {
    final result = await request('auth/bridge',
        method: 'POST', data: {'account': account});
    await saveToken(result['token'] as String);
    final saved = Map<String, dynamic>.from(result['account'] as Map);
    await _saveAccount(saved);
    unawaited(syncOutbox(force: true));
    return saved;
  }

  Future<JsonMap> snapshot() async {
    final expectedId = currentPatientId;
    final expectedToken = token;
    final expectedRevision = _sessionRevision;
    if (expectedId == null || expectedToken == null)
      throw ApiException('Sign in before synchronizing.', statusCode: 401);
    return _fetchSnapshotForSession(
        expectedId, expectedToken, expectedRevision);
  }

  bool _ownsSession(String id, String sessionToken, int revision) =>
      currentPatientId == id &&
      token == sessionToken &&
      _sessionRevision == revision;

  Future<JsonMap> _fetchSnapshotForSession(
      String expectedId, String expectedToken, int expectedRevision) async {
    final data = await request('snapshot', bearerToken: expectedToken);
    if (!_ownsSession(expectedId, expectedToken, expectedRevision))
      throw ApiException('The active session changed while synchronizing.');
    final account = Map<String, dynamic>.from(data['account'] as Map);
    if (account['id'] != expectedId)
      throw ApiException('The signed-in account does not own this local queue.',
          statusCode: 403);
    cachedAccount = Map<String, dynamic>.from(account);
    await store.write(_accountKey, jsonEncode(account));
    if (!_ownsSession(expectedId, expectedToken, expectedRevision))
      throw ApiException('The active session changed while synchronizing.');
    _serverSnapshot = Map<String, dynamic>.from(data);
    await store.write(_snapshotKey(expectedId), jsonEncode(_serverSnapshot));
    if (!_ownsSession(expectedId, expectedToken, expectedRevision))
      throw ApiException('The active session changed while synchronizing.');
    return localSnapshot();
  }

  Future<JsonMap> localSnapshot() async {
    final base = Map<String, dynamic>.from(_serverSnapshot);
    if (cachedAccount != null) base['account'] = cachedAccount;
    return currentPatientId == null
        ? base
        : _merge(base, await _loadOutbox(currentPatientId!));
  }

  Future<List<OutboxOperation>> _loadOutbox(String id) async {
    final raw = await store.read(_outboxKey(id));
    if (raw == null) return [];
    return (jsonDecode(raw) as List)
        .map((value) =>
            OutboxOperation.fromJson(Map<String, dynamic>.from(value as Map)))
        .toList();
  }

  Future<void> _saveOutbox(String id, List<OutboxOperation> operations) =>
      store.write(_outboxKey(id),
          jsonEncode(operations.map((value) => value.toJson()).toList()));

  Future<void> queueAdd(String kind, JsonMap item) async {
    final id = currentPatientId;
    if (id == null || item['patientSlug'] != id)
      throw ApiException(
          'This record does not belong to the signed-in patient.');
    final operations = await _loadOutbox(id);
    final recordId = item['id'] as String;
    if (operations.any(
        (value) => value.recordId == recordId && value.type == 'create:$kind'))
      return;
    operations.add(OutboxOperation(
        operationId: 'op-$recordId',
        recordId: recordId,
        patientId: id,
        type: 'create:$kind',
        payload: Map<String, dynamic>.from(item),
        eventAt:
            '${item['recordedAt'] ?? item['administeredAt'] ?? item['plannedEatingAt']}',
        createdAt: DateTime.now().toUtc().toIso8601String()));
    await _saveOutbox(id, operations);
    onLocalChange?.call();
    unawaited(syncOutbox());
  }

  Future<void> queueMealUpdate(String recordId, JsonMap update) async {
    final id = currentPatientId;
    if (id == null) throw ApiException('Sign in before updating a meal.');
    final operations = await _loadOutbox(id);
    final create = operations
        .where((value) =>
            value.recordId == recordId && value.type == 'create:food')
        .firstOrNull;
    final mutationId = update['mutationId'] as String;
    if (operations.any((value) => value.operationId == mutationId)) return;
    operations.add(OutboxOperation(
        operationId: mutationId,
        recordId: recordId,
        patientId: id,
        type: 'update:food',
        payload: Map<String, dynamic>.from(update),
        eventAt:
            '${update['actualEatingAt'] ?? DateTime.now().toUtc().toIso8601String()}',
        createdAt: DateTime.now().toUtc().toIso8601String(),
        dependsOn: create?.operationId));
    await _saveOutbox(id, operations);
    onLocalChange?.call();
    unawaited(syncOutbox());
  }

  Future<void> retry(String operationId) async {
    final id = currentPatientId;
    if (id == null) return;
    final operations = await _loadOutbox(id);
    final op = operations
        .where((value) => value.operationId == operationId)
        .firstOrNull;
    if (op == null) return;
    op.state = 'pending';
    op.attempts = 0;
    op.nextAttemptAt = null;
    op.errorKind = null;
    op.errorMessage = null;
    await _saveOutbox(id, operations);
    onLocalChange?.call();
    await syncOutbox(force: true);
  }

  Future<void> syncOutbox({bool force = false}) async {
    final id = currentPatientId;
    if (_syncing || id == null || token == null || authPaused) return;
    _syncing = true;
    try {
      final operations = await _loadOutbox(id);
      for (final op in List<OutboxOperation>.from(operations)) {
        if (currentPatientId != id) break;
        if (!force && (op.state == 'failed' || op.state == 'conflict'))
          continue;
        final next = DateTime.tryParse(op.nextAttemptAt ?? '');
        if (!force && next != null && next.isAfter(DateTime.now().toUtc()))
          continue;
        if (op.dependsOn != null &&
            operations.any((value) => value.operationId == op.dependsOn))
          continue;
        op.state = 'syncing';
        op.errorKind = null;
        op.errorMessage = null;
        await _saveOutbox(id, operations);
        onLocalChange?.call();
        try {
          if (op.type.startsWith('create:')) {
            await request(op.type.substring(7),
                method: 'POST', data: op.payload);
          } else {
            if (op.payload['expectedVersion'] == null)
              op.payload['expectedVersion'] =
                  _findById(_serverSnapshot['food'], op.recordId)?['version'];
            if (op.payload['expectedVersion'] == null)
              throw ApiException(
                  'Waiting for the planned meal to be confirmed by the server.',
                  network: true);
            await request('food/${Uri.encodeComponent(op.recordId)}',
                method: 'PATCH', data: op.payload);
          }
          operations.remove(op);
          await _saveOutbox(id, operations);
          try {
            await snapshot();
          } catch (_) {}
        } on ApiException catch (error) {
          var acknowledged = false;
          if (error.network || error.statusCode == 409) {
            try {
              await snapshot();
              acknowledged = _operationMatchesSnapshot(op, _serverSnapshot);
            } catch (_) {}
          }
          if (acknowledged)
            operations.remove(op);
          else if (error.statusCode == 401) {
            op.state = 'pending';
            op.errorKind = 'authentication';
            op.errorMessage = 'Sign in again to resume synchronization.';
            authPaused = true;
          } else if (error.statusCode == 409) {
            op.state = 'conflict';
            op.errorKind = 'conflict';
            op.errorMessage =
                'The server has a different version. Review before retrying.';
          } else if (!error.network &&
              error.statusCode != null &&
              error.statusCode! >= 400 &&
              error.statusCode! < 500 &&
              error.statusCode != 408 &&
              error.statusCode != 429) {
            op.state = 'failed';
            op.errorKind = 'validation';
            op.errorMessage = error.message;
          } else {
            op.state = 'pending';
            op.attempts += 1;
            op.errorKind = 'network';
            op.errorMessage = 'Saved on this device; waiting to sync.';
            op.nextAttemptAt = DateTime.now()
                .toUtc()
                .add(Duration(seconds: min(300, 1 << min(op.attempts, 8))))
                .toIso8601String();
          }
          await _saveOutbox(id, operations);
        }
        onLocalChange?.call();
      }
    } finally {
      _syncing = false;
    }
  }

  bool _operationMatchesSnapshot(OutboxOperation op, JsonMap snapshot) {
    final kind = op.type == 'update:food' ? 'food' : op.type.substring(7);
    final found = _findById(snapshot[kind], op.recordId);
    if (found == null) return false;
    if (op.type == 'update:food') {
      if (found['status'] != op.payload['status']) return false;
      if (op.payload.containsKey('consumedCarbsG') &&
          !_sameNumber(found['consumedCarbsG'], op.payload['consumedCarbsG']))
        return false;
      return op.payload['status'] == 'cancelled' ||
          _sameInstant(found['actualEatingAt'], op.payload['actualEatingAt']);
    }
    final sent = op.payload;
    return switch (kind) {
      'glucose' => _sameNumber(found['value'], sent['value']) &&
          _sameInstant(found['recordedAt'], sent['recordedAt']),
      'bolus' => _sameNumber(found['administeredUnits'] ?? found['recorded'],
              sent['administeredUnits'] ?? sent['recorded']) &&
          _sameInstant(found['administeredAt'], sent['administeredAt']),
      'food' => found['status'] == sent['status'] &&
          _sameNumber(found['announcedCarbsG'] ?? found['carbs'],
              sent['announcedCarbsG'] ?? sent['carbs']) &&
          _sameInstant(found['plannedEatingAt'], sent['plannedEatingAt']),
      _ => false,
    };
  }

  JsonMap _merge(JsonMap base, List<OutboxOperation> operations) {
    final result = Map<String, dynamic>.from(base);
    for (final key in ['glucose', 'bolus', 'food']) {
      result[key] = ((base[key] as List?) ?? [])
          .map((value) => {
                ...Map<String, dynamic>.from(value as Map),
                'syncState': 'synced'
              })
          .toList();
    }
    for (final op in operations) {
      final key = op.type == 'update:food' ? 'food' : op.type.substring(7);
      final rows = (result[key] as List).cast<JsonMap>();
      JsonMap? item;
      for (final row in rows) {
        if (row['id'] == op.recordId) {
          item = row;
          break;
        }
      }
      if (op.type.startsWith('create:')) {
        item ??= Map<String, dynamic>.from(op.payload);
        if (!rows.any((row) => row['id'] == op.recordId)) {
          rows.insert(0, item);
        } else {
          item.addAll(op.payload);
        }
      } else if (item != null) {
        item.addAll(op.payload);
        if (op.payload['status'] == 'cancelled') {
          item['consumedCarbsG'] = null;
          item['actualEatingAt'] = null;
        }
      }
      if (item != null) {
        item['syncState'] = op.state;
        item['syncOperationId'] = op.operationId;
        item['syncError'] = op.errorMessage;
      }
    }
    return result;
  }

  JsonMap? _findById(dynamic rows, String id) {
    if (rows is! List) return null;
    for (final raw in rows) {
      final item = raw as Map;
      if (item['id'] == id) return Map<String, dynamic>.from(item);
    }
    return null;
  }

  bool _sameInstant(dynamic a, dynamic b) {
    final left = DateTime.tryParse('$a');
    final right = DateTime.tryParse('$b');
    return left != null && right != null && left.toUtc() == right.toUtc();
  }

  bool _sameNumber(dynamic a, dynamic b) {
    num? parse(dynamic value) {
      if (value is num) return value;
      return num.tryParse(
          RegExp(r'-?\d+(?:\.\d+)?').firstMatch('$value')?.group(0) ?? '');
    }

    return parse(a) == parse(b);
  }

  Future<List<dynamic>> doctors() async =>
      (await request('doctors'))['doctors'] as List<dynamic>;
  Future<void> requestDoctor(String doctorId) async {
    await request('patient/doctor-request',
        method: 'POST', data: {'doctorId': doctorId});
  }

  Future<void> add(String kind, JsonMap item) async {
    await request(kind, method: 'POST', data: item);
  }

  Future<JsonMap> updateMeal(String id, JsonMap update) async =>
      Map<String, dynamic>.from((await request(
          'food/${Uri.encodeComponent(id)}',
          method: 'PATCH',
          data: update))['meal'] as Map);
  Future<List<JsonMap>> emergencyContacts() async =>
      ((await request('emergency-contacts'))['contacts'] as List)
          .map((value) => Map<String, dynamic>.from(value as Map))
          .toList();
  Future<void> createEmergencyContact(JsonMap contact) async {
    await request('emergency-contacts', method: 'POST', data: contact);
  }

  Future<void> updateEmergencyContact(String id, JsonMap contact) async {
    await request('emergency-contacts/${Uri.encodeComponent(id)}',
        method: 'PUT', data: contact);
  }

  Future<void> deleteEmergencyContact(String id) async {
    await request('emergency-contacts/${Uri.encodeComponent(id)}',
        method: 'DELETE');
  }
}
