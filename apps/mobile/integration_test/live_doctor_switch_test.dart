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

  testWidgets('explicit doctor switch closes old chat and creates pending request',
      (tester) async {
    await tester.pumpWidget(const PatientMobileApp());
    await waitFor(tester, find.text('Sign in'));
    await tester.tap(find.text('Sign in').first);
    await tester.pumpAndSettle();
    await tester.enterText(field('Email'), email);
    await tester.enterText(field('Password'), password);
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await waitFor(tester, find.text('Hello, iOS Browser Accepted Patient'));
    await tester.tap(find.text('Care').last);
    await tester.pumpAndSettle();
    await waitFor(tester, find.text('Request: accepted'));

    await tester.tap(find.text('Find another doctor'));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Dr. Khaled Mansour'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Send request'));
    await tester.pumpAndSettle();
    await waitFor(tester, find.text('Request: pending'));
    expect(find.textContaining('Dr. Khaled Mansour'), findsWidgets);
    expect(find.text('Messaging opens after your doctor accepts your request.'),
        findsOneWidget);
    expect(field('Message your doctor'), findsNothing);
  });
}
