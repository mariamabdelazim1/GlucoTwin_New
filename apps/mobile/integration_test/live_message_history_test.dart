import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:glucotwin/patient_app.dart';

const patientName = 'iOS Browser Accepted Patient';
const doctorReply = 'Synthetic doctor reply from real website';
const email = 'ios.accept.20261111.run4@example.test';
const password = 'SyntheticPass123!';

Finder field(String label) => find.byWidgetPredicate((widget) =>
    widget is TextField && widget.decoration?.labelText == label);

Future<void> waitFor(WidgetTester tester, Finder finder,
    {Duration timeout = const Duration(seconds: 30)}) async {
  final end = DateTime.now().add(timeout);
  while (finder.evaluate().isEmpty && DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 500));
  }
  expect(finder, findsWidgets, reason: 'Timed out waiting for $finder');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('doctor reply survives an app restart', (tester) async {
    await tester.pumpWidget(const PatientMobileApp());
    await tester.pump(const Duration(seconds: 2));
    if (find.text('Hello, $patientName').evaluate().isEmpty) {
      await tester.tap(find.text('Sign in').first);
      await tester.pumpAndSettle();
      await tester.enterText(field('Email'), email);
      await tester.enterText(field('Password'), password);
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    }
    await waitFor(tester, find.text('Hello, $patientName'));
    await tester.tap(find.text('Care').last);
    await tester.pumpAndSettle();
    await waitFor(tester, find.text('Request: accepted'));
    await waitFor(tester, find.text(doctorReply));
  });
}
