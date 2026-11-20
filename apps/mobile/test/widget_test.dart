import 'package:flutter_test/flutter_test.dart';
import 'package:glucotwin/patient_app.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:glucotwin/data/sync_api.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:glucotwin/presentation/widgets/bolus_recommendation_card.dart';
import 'package:glucotwin/presentation/widgets/portal_message_bubble.dart';
import 'package:glucotwin/core/constants/app_colors.dart';

void main() {
  test('mobile clinical payloads match the units-only and eaten-food contracts',
      () {
    final submittedAt = DateTime.parse('2026-11-19T11:12:00+02:00');
    final bolus = buildMobileBolusEntry(
        id: 'dose-1',
        patientId: 'p1',
        patientName: 'Patient',
        units: 2.5,
        submittedAt: submittedAt,
        localTimeLabel: '1:12 PM');
    expect(bolus['administeredAt'], '2026-11-19T09:12:00.000Z');
    expect(bolus['administeredUnits'], 2.5);
    expect(bolus.containsKey('meal'), isFalse);
    expect(bolus.containsKey('mealId'), isFalse);
    expect(bolus.containsKey('carbs'), isFalse);
    expect(bolus.containsKey('carbsG'), isFalse);

    final food = buildMobileFoodEntry(
        id: 'meal-1',
        patientId: 'p1',
        patientName: 'Patient',
        meal: 'Lunch',
        items: 'Oats',
        carbs: 0,
        submittedAt: submittedAt,
        localTimeLabel: '1:12 PM');
    expect(food, containsPair('status', 'eaten'));
    expect(food, containsPair('announcedCarbsG', 0));
    expect(food, containsPair('consumedCarbsG', 0));
    expect(food['actualEatingAt'], food['plannedEatingAt']);
    expect(food.containsKey('glucose'), isFalse);
  });

  test(
      'clinical history uses stored timestamps and keeps missing dates visible',
      () {
    final rows = <Map<String, dynamic>>[
      {'id': 'legacy'},
      {'id': 'before', 'administeredAt': '2026-11-18T23:55:00Z'},
      {'id': 'after', 'administeredAt': '2026-11-19T00:05:00Z'},
    ]..sort((a, b) =>
        compareClinicalHistory(a, b, (item) => item['administeredAt']));
    expect(rows.map((item) => item['id']), ['after', 'before', 'legacy']);
    expect(formatClinicalDateTime(null), 'Date unavailable');
    expect(
        foodHistoryDateLabel(
            {'status': 'planned', 'plannedEatingAt': '2026-11-18T23:55:00Z'}),
        startsWith('Planned: '));
    expect(foodHistoryDateLabel({'status': 'cancelled'}),
        'Planned: Date unavailable');
  });

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
    expect(find.text('Care-team messages'), findsNothing);
    expect(find.text('My medical info'), findsNothing);
    expect(find.text('Latest manual reading'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('bolus recommendation switches states and opens matching details',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(child: BolusRecommendationCard()),
        ),
      ),
    );

    expect(find.text('Bolus Recommendation'), findsOneWidget);
    expect(find.text('Lunch · 45 g carbs'), findsOneWidget);
    expect(find.text('Meal bolus estimate'), findsOneWidget);
    expect(find.text('— U'), findsOneWidget);

    await tester.tap(find.text('High glucose').first);
    await tester.pumpAndSettle();
    expect(find.text('Glucose above your target'), findsOneWidget);
    expect(find.text('214 mg/dL · Sample reading at 23:00'), findsOneWidget);
    expect(find.text('Correction bolus estimate'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('bolus-recommendation-review')));
    await tester.pumpAndSettle();
    expect(find.text('High glucose inputs'), findsOneWidget);
    expect(find.text('70–180 mg/dL'), findsOneWidget);
    expect(find.text('Visual prototype only. No dose is calculated or saved.'),
        findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'portal message bubbles style existing and newly sent outgoing messages',
      (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              PortalMessageBubble(text: 'Existing outgoing', outgoing: true),
              PortalMessageBubble(text: 'Newly sent outgoing', outgoing: true),
              PortalMessageBubble(text: 'Incoming message', outgoing: false),
            ],
          ),
        ),
      ),
    );

    BoxDecoration decorationFor(String text) {
      final container = tester.widget<Container>(find
          .ancestor(of: find.text(text), matching: find.byType(Container))
          .first);
      return container.decoration! as BoxDecoration;
    }

    for (final text in ['Existing outgoing', 'Newly sent outgoing']) {
      final decoration = decorationFor(text);
      expect(decoration.color, AppColors.portalIceBlue);
      expect(decoration.border!.top.color, AppColors.portalBorder);
      expect(tester.widget<Text>(find.text(text)).style!.color,
          AppColors.portalNavy);
    }
    final incoming = decorationFor('Incoming message');
    expect(incoming.color, Colors.white);
    expect(incoming.border!.top.color, AppColors.portalBorder);
  });

  testWidgets('record screen exposes simplified food and bolus entry controls',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(
        home: PatientPortal(
      api: SyncApi(),
      account: const {
        'id': 'p1',
        'patientProfile': {'fullName': 'Patient'}
      },
      snapshot: const {'food': [], 'bolus': [], 'glucose': []},
      error: null,
      onRefresh: () async {},
      onLocalChange: () async {},
      onSignOut: () async {},
    )));
    await tester.tap(find.text('Record').last);
    await tester.pumpAndSettle();
    expect(find.text('Glucose'), findsNothing);

    await tester.tap(find.text('Log bolus'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextField, 'Bolus units'), findsOneWidget);
    expect(find.text('Meal'), findsNothing);
    expect(find.text('Carbs (g, optional)'), findsNothing);
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(find.text('Enter a finite, non-negative insulin dose.'),
        findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Bolus units'), '-1');
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(find.text('Enter a finite, non-negative insulin dose.'),
        findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Add food'));
    await tester.pumpAndSettle();
    expect(find.text('Meal'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Food items'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Carbs g'), findsOneWidget);
    expect(find.text('Plan for later'), findsNothing);
    expect(find.text('Already eaten'), findsNothing);
    expect(find.text('Glucose'), findsNothing);
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
    final incoming = tester.widget<Container>(find
        .ancestor(
            of: find.text('Oldest message'), matching: find.byType(Container))
        .first);
    final outgoing = tester.widget<Container>(find
        .ancestor(
            of: find.text('Newest message'), matching: find.byType(Container))
        .first);
    expect((incoming.decoration as BoxDecoration).color, Colors.white);
    expect((incoming.decoration as BoxDecoration).border!.top.color,
        AppColors.portalBorder);
    expect(
        (outgoing.decoration as BoxDecoration).color, AppColors.portalIceBlue);
    expect((outgoing.decoration as BoxDecoration).border!.top.color,
        AppColors.portalBorder);
    expect(find.byType(PortalMessageBubble), findsNWidgets(2));
  });
}
