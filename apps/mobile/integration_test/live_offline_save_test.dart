import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:glucotwin/patient_app.dart';

const email = 'ios.accept.20261111.run4@example.test';
const password = 'SyntheticPass123!';

Finder field(String label) => find.byWidgetPredicate((widget) =>
    widget is TextField && widget.decoration?.labelText == label);

Future<void> waitFor(WidgetTester tester, Finder finder,
    {Duration timeout = const Duration(seconds: 25)}) async {
  final end = DateTime.now().add(timeout);
  while (finder.evaluate().isEmpty && DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 250));
  }
  expect(finder, findsWidgets, reason: 'Timed out waiting for $finder');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('offline glucose save is not shown as successful', (tester) async {
    await tester.pumpWidget(const PatientMobileApp());
    await waitFor(tester, find.text('Sign in'));
    await tester.tap(find.text('Sign in').first);
    await tester.pumpAndSettle();
    await tester.enterText(field('Email'), email);
    await tester.enterText(field('Password'), password);
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await waitFor(tester, find.text('Hello, iOS Browser Accepted Patient'));
    await tester.tap(find.text('Record').last);
    await tester.pumpAndSettle();

    debugPrint('OFFLINE_PHASE_READY');
    await Future<void>.delayed(const Duration(seconds: 20));
    await tester.tap(find.text('Record reading'));
    await tester.pumpAndSettle();
    await tester.enterText(field('Glucose mg/dL'), '211');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));

    expect(find.textContaining('211'), findsNothing);
    expect(find.byWidgetPredicate((widget) => widget is Text &&
      ((widget.data ?? '').contains('Connection') ||
       (widget.data ?? '').contains('ClientException'))), findsWidgets);
  });
}
