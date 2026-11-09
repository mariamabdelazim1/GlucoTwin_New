import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class SyncApi {
  static const configuredBaseUrl = String.fromEnvironment('API_BASE_URL');
  static String get baseUrl => configuredBaseUrl.isNotEmpty
      ? configuredBaseUrl
      : kIsWeb ? 'http://127.0.0.1:8787' : 'http://10.0.2.2:8787';
  String? token;

  Future<void> restore() async {
    token = (await SharedPreferences.getInstance()).getString('patient_sync_token');
  }
  Future<void> saveToken(String value) async {
    token = value;
    (await SharedPreferences.getInstance()).setString('patient_sync_token', value);
  }
  Future<void> signOut() async {
    token = null;
    (await SharedPreferences.getInstance()).remove('patient_sync_token');
  }
  Future<Map<String, dynamic>> request(String path, {String method = 'GET', Map<String, dynamic>? data}) async {
    final client = http.Client();
    try {
      final request = http.Request(method, Uri.parse('$baseUrl/api/$path'));
      request.headers['Content-Type'] = 'application/json';
      if (token != null) request.headers['Authorization'] = 'Bearer $token';
      if (data != null) request.body = jsonEncode(data);
      final response = await http.Response.fromStream(await client.send(request));
      final result = jsonDecode(response.body) as Map<String, dynamic>;
      if (response.statusCode >= 400) throw Exception(result['error'] ?? 'Sync request failed');
      return result;
    } finally { client.close(); }
  }
  Future<Map<String, dynamic>> login(String email, String password) async {
    final result = await request('auth/login', method: 'POST', data: {'email': email, 'password': password});
    await saveToken(result['token'] as String);
    return result['account'] as Map<String, dynamic>;
  }
  Future<Map<String, dynamic>> register(Map<String, dynamic> account) async {
    final result = await request('auth/bridge', method: 'POST', data: {'account': account});
    await saveToken(result['token'] as String);
    return result['account'] as Map<String, dynamic>;
  }
  Future<Map<String, dynamic>> snapshot() => request('snapshot');
  Future<List<dynamic>> doctors() async => (await request('doctors'))['doctors'] as List<dynamic>;
  Future<void> requestDoctor(String doctorId) async { await request('patient/doctor-request', method: 'POST', data: {'doctorId': doctorId}); }
  Future<void> add(String kind, Map<String, dynamic> item) async { await request(kind, method: 'POST', data: item); }
  Future<Map<String, dynamic>> updateMeal(String id, Map<String, dynamic> update) async =>
      (await request('food/${Uri.encodeComponent(id)}', method: 'PATCH', data: update))['meal'] as Map<String, dynamic>;
}
