import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:glucotwin/patient_app.dart';

const email = String.fromEnvironment('UI_TEST_EMAIL',
    defaultValue: 'ios.accept.20261111@example.test');
const patientName = String.fromEnvironment('UI_TEST_NAME',
    defaultValue: 'iOS Acceptance Patient');
const password = 'SyntheticPass123!';

Finder field(String label) => find.byWidgetPredicate((widget) =>
    widget is TextField && widget.decoration?.labelText == label);

Future<void> waitFor(WidgetTester tester, Finder finder,
    {Duration timeout = const Duration(seconds: 20)}) async {
  final end = DateTime.now().add(timeout);
  while (finder.evaluate().isEmpty && DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 250));
  }
  expect(finder, findsWidgets, reason: 'Timed out waiting for $finder');
}

Future<void> tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder.first);
  await tester.tap(finder.first);
  await tester.pumpAndSettle();
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('real iOS patient journey writes and reloads clinical records',
      (tester) async {
    await tester.pumpWidget(const PatientMobileApp());
    await waitFor(tester, find.text('New patient? Create account'));
    await tapVisible(tester, find.text('New patient? Create account'));
    await waitFor(tester, field('Full name'));

    await tester.enterText(field('Full name'), patientName);
    await tester.enterText(field('Age'), '31');
    await tester.enterText(field('Weight kg'), '68');
    await tester.enterText(field('Height cm'), '170');
    await tester.enterText(field('Email'), email);
    await tester.enterText(field('Password'), password);
    await waitFor(tester, find.textContaining('Dr. Sarah'));
    await tapVisible(tester, find.textContaining('Dr. Sarah'));
    await tapVisible(tester, find.text('Create account'));

    await waitFor(tester, find.text('Hello, $patientName'));
    await tapVisible(tester, find.text('Care'));
    await waitFor(tester, find.text('Request: pending'));
    expect(find.text('Messaging opens after your doctor accepts your request.'),
        findsOneWidget);

    await tapVisible(tester, find.text('Record'));
    await tapVisible(tester, find.text('Record reading'));
    await tester.enterText(field('Glucose mg/dL'), '143');
    await tapVisible(tester, find.text('Save'));
    await waitFor(tester, find.textContaining('143'));

    await tapVisible(tester, find.text('Log bolus'));
    await tester.enterText(field('Carbs g'), '42');
    await tester.enterText(field('Pre-meal glucose mg/dL'), '143');
    await tester.enterText(field('Bolus units'), '4.5');
    await tapVisible(tester, find.text('Save'));
    await waitFor(tester, find.textContaining('4.5 U at'));

    await tapVisible(tester, find.text('Add food'));
    await tester.enterText(field('Food items'), 'Synthetic planned meal');
    await tester.enterText(field('Carbs g'), '42');
    await tapVisible(tester, find.text('Save'));
    await waitFor(tester, find.textContaining('Synthetic planned meal'));
    expect(find.textContaining('42g carbs · planned'), findsOneWidget);

    await tapVisible(tester, find.text('Profile'));
    await tapVisible(tester, find.text('Add contact'));
    await tester.enterText(field('Name'), 'Synthetic Contact One');
    await tester.enterText(field('Relationship'), 'Sibling');
    await tester.enterText(field('Phone with country code'), '+201000000001');
    await tapVisible(tester, find.text('Primary contact'));
    await tapVisible(tester, find.text('Save'));
    await waitFor(tester, find.textContaining('Synthetic Contact One'));

    final profileList = find.byType(ListView).last;
    await tester.drag(profileList, const Offset(0, -600));
    await tester.pumpAndSettle();
    await tester.drag(profileList, const Offset(0, -400));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Sign out'));
    await tester.pumpAndSettle();
    await tapVisible(tester, find.text('Sign in'));
    await waitFor(tester, field('Email'));
    await tester.enterText(field('Email'), email);
    await tester.enterText(field('Password'), 'wrong-password');
    await tapVisible(tester, find.text('Sign in'));
    await waitFor(tester, find.textContaining('Incorrect'));
    await tester.enterText(field('Password'), password);
    await tapVisible(tester, find.text('Sign in'));
    await waitFor(tester, find.text('Hello, $patientName'));
    await tapVisible(tester, find.text('Record'));
    expect(find.textContaining('143'), findsWidgets);
    expect(find.textContaining('Synthetic planned meal'), findsOneWidget);
  });
}
