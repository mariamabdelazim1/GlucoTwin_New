import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:glucotwin/patient_app.dart';

const email = 'ios.accept.20261111.run4@example.test';
const password = 'SyntheticPass123!';

Finder field(String label) => find.byWidgetPredicate(
    (widget) => widget is TextField && widget.decoration?.labelText == label);

Future<void> waitFor(WidgetTester tester, Finder finder,
    {Duration timeout = const Duration(seconds: 25)}) async {
  final end = DateTime.now().add(timeout);
  while (finder.evaluate().isEmpty && DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 250));
  }
  expect(finder, findsWidgets, reason: 'Timed out waiting for $finder');
}

Future<void> bringIntoView(WidgetTester tester, Finder finder) async {
  for (var attempt = 0; attempt < 12; attempt++) {
    final rect = tester.getRect(finder.first);
    if (rect.top >= 110 && rect.bottom <= 750) return;
    await tester.drag(
        find.byType(ListView).first, Offset(0, rect.top < 110 ? 280 : -280));
    await tester.pumpAndSettle();
  }
  fail('Could not bring $finder into the tappable viewport.');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
      'offline glucose is durably queued and not presented as doctor-visible',
      (tester) async {
    await tester.pumpWidget(const PatientMobileApp());
    final restored = find.text('Hello, iOS Browser Accepted Patient');
    final startDeadline = DateTime.now().add(const Duration(seconds: 25));
    while (find.text('Sign in').evaluate().isEmpty &&
        restored.evaluate().isEmpty &&
        DateTime.now().isBefore(startDeadline)) {
      await tester.pump(const Duration(milliseconds: 250));
    }
    if (restored.evaluate().isEmpty) {
      expect(find.text('Sign in'), findsWidgets,
          reason: 'Neither the cached session nor sign-in screen appeared.');
      await tester.tap(find.text('Sign in').first);
      await tester.pumpAndSettle();
      await tester.enterText(field('Email'), email);
      await tester.enterText(field('Password'), password);
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    }
    await waitFor(tester, find.text('Hello, iOS Browser Accepted Patient'));
    await tester.tap(find.text('Record').last);
    await tester.pumpAndSettle();

    debugPrint('OFFLINE_PHASE_READY');
    await Future<void>.delayed(const Duration(seconds: 30));
    await tester.tap(find.text('Record reading'));
    await tester.pumpAndSettle();
    await tester.enterText(field('Glucose mg/dL'), '223');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));

    await bringIntoView(tester, find.text('Log bolus'));
    await tester.tap(find.text('Log bolus'));
    await tester.pumpAndSettle();
    await tester.enterText(field('Bolus units'), '3');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    await bringIntoView(tester, find.text('Add food'));
    await tester.tap(find.text('Add food'));
    await tester.pumpAndSettle();
    await tester.enterText(field('Food items'), 'Offline rice');
    await tester.enterText(field('Carbs g'), '40');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    await bringIntoView(tester, find.text('Mark eaten').first);
    await tester.tap(find.text('Mark eaten').first);
    await tester.pumpAndSettle();
    await tester.enterText(field('Consumed carbs g'), '35');
    await tester.tap(find.text('Confirm'));
    await tester.pumpAndSettle();

    expect(find.textContaining('223'), findsWidgets);
    expect(find.textContaining('3 U'), findsWidgets);
    expect(find.textContaining('Offline rice'), findsWidgets);
    expect(
        find.byWidgetPredicate((widget) =>
            widget is Text &&
            ((widget.data ?? '').contains('Saved on this device') ||
                (widget.data ?? '').contains('Syncing'))),
        findsWidgets);
    expect(find.textContaining('visible to your doctor'), findsNothing);

    debugPrint('OFFLINE_QUEUED_READY');
    await Future<void>.delayed(const Duration(seconds: 20));
    final syncDeadline = DateTime.now().add(const Duration(seconds: 25));
    final pending = find.text('Saved on this device; waiting to sync');
    while (pending.evaluate().isNotEmpty &&
        DateTime.now().isBefore(syncDeadline)) {
      await tester.pump(const Duration(milliseconds: 500));
    }
    expect(pending, findsNothing,
        reason:
            'The queued reading did not synchronize after the API returned.');
    expect(find.text('Synced'), findsWidgets,
        reason:
            'The synchronized reading did not display its acknowledged state.');
    expect(find.textContaining('223'), findsWidgets);
    debugPrint('OFFLINE_SYNCED_READY');
    await Future<void>.delayed(const Duration(seconds: 30));
  });
}
