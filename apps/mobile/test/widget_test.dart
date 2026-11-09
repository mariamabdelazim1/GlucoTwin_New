import 'package:flutter_test/flutter_test.dart';
import 'package:glucotwin/patient_app.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:glucotwin/data/sync_api.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(
      const PatientMobileApp(),
    );
    expect(find.byType(PatientMobileApp), findsOneWidget);
  });
  testWidgets('Shared demo renders CGM and forecast at phone size', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final demo = jsonDecode(File('../web/src/data/demoPatient.json').readAsStringSync()) as Map<String, dynamic>;
    await tester.pumpWidget(MaterialApp(home: PatientPortal(
      api: SyncApi(), account: const {'id': 'omar-hassan', 'email': 'omar.hassan@example.com', 'patientProfile': {'fullName': 'Omar Hassan', 'age': '34', 'weight': '82', 'height': '178'}},
      snapshot: {'demo': demo, 'food': demo['food'], 'bolus': demo['bolus']}, error: null,
      onRefresh: () async {}, onSignOut: () async {},
    )));
    await tester.pumpAndSettle();
    expect(find.text('CGM graph'), findsOneWidget);
    expect(find.text('Digital twin forecast · demo'), findsOneWidget);
    expect(find.byType(LineChart), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });
}
