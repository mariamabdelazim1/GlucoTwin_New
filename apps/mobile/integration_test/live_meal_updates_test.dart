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

  testWidgets('planned meals can be confirmed and cancelled through iOS',
      (tester) async {
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

    await waitFor(tester, find.textContaining('Synthetic planned meal'));
    final plannedTile = find.ancestor(
      of: find.textContaining('Synthetic planned meal').first,
      matching: find.byType(ListTile),
    );
    await tester.tap(find.descendant(of: plannedTile, matching: find.text('Mark eaten')));
    await tester.pumpAndSettle();
    await waitFor(tester, find.textContaining('42g carbs · eaten'));

    await tester.tap(find.text('Add food'));
    await tester.pumpAndSettle();
    await tester.enterText(field('Food items'), 'Synthetic cancelled meal');
    await tester.enterText(field('Carbs g'), '31');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    await waitFor(tester, find.textContaining('Synthetic cancelled meal'));
    final cancelledTile = find.ancestor(
      of: find.textContaining('Synthetic cancelled meal').first,
      matching: find.byType(ListTile),
    );
    await tester.tap(find.descendant(of: cancelledTile, matching: find.text('Cancel')));
    await tester.pumpAndSettle();
    await waitFor(tester, find.textContaining('31g carbs · cancelled'));
  });
}
