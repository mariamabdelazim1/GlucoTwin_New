import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:glucotwin/patient_app.dart';

const patientName = 'iOS Browser Declined Patient';
const email = 'ios.decline.20261111@example.test';
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

Future<void> login(WidgetTester tester) async {
  await tester.tap(find.text('Sign in').first);
  await tester.pumpAndSettle();
  await tester.enterText(field('Email'), email);
  await tester.enterText(field('Password'), password);
  await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
  await waitFor(tester, find.text('Hello, $patientName'));
}

Future<void> verifyDeclined(WidgetTester tester) async {
  await tester.tap(find.text('Care').last);
  await tester.pumpAndSettle();
  await waitFor(tester, find.text('Request: declined'));
  expect(find.text('Messaging opens after your doctor accepts your request.'),
      findsOneWidget);
  expect(field('Message your doctor'), findsNothing);
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('declined request stays declined after logout and login',
      (tester) async {
    await tester.pumpWidget(const PatientMobileApp());
    await waitFor(tester, find.text('Sign in'));
    await login(tester);
    await verifyDeclined(tester);

    await tester.tap(find.text('Profile').last);
    await tester.pumpAndSettle();
    final profileList = find.byType(ListView).last;
    await tester.drag(profileList, const Offset(0, -900));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Sign out'));
    await tester.pumpAndSettle();

    await login(tester);
    await verifyDeclined(tester);
  });
}
