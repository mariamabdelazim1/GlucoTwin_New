import 'package:flutter_test/flutter_test.dart';
import 'package:glucotwin/patient_app.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:glucotwin/data/sync_api.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

void main() {
  test('conversation messages use full timestamps with a stable ID tie-breaker',
      () {
    final rows = chronologicalConversationMessages([
      {'id': 'z', 'sentAt': '2026-11-09T23:24:00Z', 'time': '11:24 PM'},
      {'id': 'b', 'sentAt': '2026-11-09T23:23:00Z', 'time': 'Now'},
      {'id': 'a', 'sentAt': '2026-11-09T23:23:00Z', 'time': '11:23 PM'},
    ]);
    expect(rows.map((row) => row['id']), ['a', 'b', 'z']);
  });

  testWidgets('App smoke test', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    await tester.pumpWidget(
      const PatientMobileApp(),
    );
    expect(find.byType(PatientMobileApp), findsOneWidget);
  });
  testWidgets('Shared demo renders CGM and forecast at phone size',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final demo =
        jsonDecode(File('../web/src/data/demoPatient.json').readAsStringSync())
            as Map<String, dynamic>;
    await tester.pumpWidget(MaterialApp(
        home: PatientPortal(
      api: SyncApi(),
      account: const {
        'id': 'omar-hassan',
        'email': 'omar.hassan@example.com',
        'patientProfile': {
          'fullName': 'Omar Hassan',
          'age': '34',
          'weight': '82',
          'height': '178'
        }
      },
      snapshot: {'demo': demo, 'food': demo['food'], 'bolus': demo['bolus']},
      error: null,
      onRefresh: () async {},
      onLocalChange: () async {},
      onSignOut: () async {},
    )));
    await tester.pumpAndSettle();
    expect(find.text('CGM graph'), findsOneWidget);
    expect(find.text('Digital twin forecast · demo'), findsOneWidget);
    expect(find.byType(LineChart), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('patient conversation is chronological in the Care screen',
      (tester) async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    await tester.pumpWidget(MaterialApp(
        home: PatientPortal(
      api: SyncApi(),
      account: const {
        'id': 'p1',
        'email': 'p1@example.test',
        'patientProfile': {'fullName': 'Patient', 'selectedDoctorId': 'd1'}
      },
      snapshot: const {
        'assignments': [
          {'patientId': 'p1', 'doctorId': 'd1', 'status': 'accepted'}
        ],
        'doctors': [
          {
            'id': 'd1',
            'doctorProfile': {'fullName': 'Doctor'}
          }
        ],
        'messages': [
          {
            'id': 'new',
            'from': 'patient',
            'text': 'Newest message',
            'sentAt': '2026-11-09T23:24:00Z'
          },
          {
            'id': 'old',
            'from': 'doctor',
            'text': 'Oldest message',
            'sentAt': '2026-11-09T23:23:00Z'
          }
        ]
      },
      error: null,
      onRefresh: () async {},
      onLocalChange: () async {},
      onSignOut: () async {},
    )));
    await tester.pump();
    await tester.tap(find.text('Care'));
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.text('Oldest message')).dy,
        lessThan(tester.getTopLeft(find.text('Newest message')).dy));
  });
}
