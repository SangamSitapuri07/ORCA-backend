import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/app.dart';
import 'package:orca_app/core/cache/cache_service.dart';

void main() {
  testWidgets('OrcaApp boots with six fisher-facing areas', (tester) async {
    final cache = CacheService();
    await cache.put(
      'app.onboarding',
      <String, dynamic>{'complete': true},
      ttl: const Duration(days: 1),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [cacheServiceProvider.overrideWithValue(cache)],
        child: const OrcaApp(),
      ),
    );
    await tester.pump();

    expect(find.text('ORCA ADVISORY'), findsOneWidget);
    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Map'), findsOneWidget);
    expect(find.text('AI Trace'), findsOneWidget);
    expect(find.text('Alerts'), findsOneWidget);
    expect(find.text('Navigate'), findsOneWidget);
    expect(find.text('Info'), findsOneWidget);

    await tester.tap(find.text('AI Trace'));
    await tester.pump();
    expect(find.text('ORCA AI AGENTS'), findsOneWidget);

    await tester.tap(find.text('Alerts'));
    await tester.pump();
    expect(find.text('MARINE ALERTS'), findsOneWidget);

    await tester.tap(find.text('Navigate'));
    await tester.pump();
    expect(find.text('ROUTE NAVIGATION'), findsOneWidget);

    await tester.tap(find.text('Info'));
    await tester.pump();
    expect(find.text('SYSTEM & DATA HEALTH'), findsOneWidget);
  });
}
