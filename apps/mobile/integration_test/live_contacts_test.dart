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

Future<void> openMenu(WidgetTester tester, String contactName) async {
  final tile = find.ancestor(
    of: find.textContaining(contactName).first,
    matching: find.byType(ListTile),
  );
  await tester.tap(find.descendant(
    of: tile,
    matching: find.byType(PopupMenuButton<String>),
  ));
  await tester.pumpAndSettle();
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('contacts add edit primary and delete work through iOS',
      (tester) async {
    await tester.pumpWidget(const PatientMobileApp());
    await waitFor(tester, find.text('Sign in'));
    await tester.tap(find.text('Sign in').first);
    await tester.pumpAndSettle();
    await tester.enterText(field('Email'), email);
    await tester.enterText(field('Password'), password);
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await waitFor(tester, find.text('Hello, iOS Browser Accepted Patient'));
    await tester.tap(find.text('Profile').last);
    await tester.pumpAndSettle();

    final list = find.byType(ListView).last;
    await tester.drag(list, const Offset(0, -650));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add contact'));
    await tester.pumpAndSettle();
    await tester.enterText(field('Name'), 'Synthetic Contact Two');
    await tester.enterText(field('Relationship'), 'Parent');
    await tester.enterText(field('Phone with country code'), '+201000000002');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    await waitFor(tester, find.textContaining('Synthetic Contact Two'));

    await openMenu(tester, 'Synthetic Contact Two');
    await tester.tap(find.text('Make primary'));
    await tester.pumpAndSettle();
    await waitFor(tester, find.textContaining('Synthetic Contact Two · Primary'));

    await openMenu(tester, 'Synthetic Contact Two');
    await tester.tap(find.text('Edit'));
    await tester.pumpAndSettle();
    await tester.enterText(field('Name'), 'Synthetic Contact Two Edited');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    await waitFor(tester, find.textContaining('Synthetic Contact Two Edited · Primary'));

    await openMenu(tester, 'Synthetic Contact One');
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Synthetic Contact One'), findsNothing);
  });
}
