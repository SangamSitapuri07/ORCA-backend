import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/cache/staleness.dart';
import 'package:orca_app/features/advisory/domain/entities/advisory.dart';
import 'package:orca_app/features/advisory/presentation/widgets/verdict_card.dart';

void main() {
  testWidgets('VerdictCard renders verdict, shape icon, headline, and plain bullets', (tester) async {
    final fakeAdvisory = AdvisoryEntity(
      verdict: 'caution',
      colorHex: '#fbbf24',
      headline: 'Moderate sea state (2.6 m waves).',
      headlineHi: 'मध्यम समुद्री स्थिति।',
      plainEn: [
        'Wave height is 2.6m exceeding 2.5m threshold',
        'Wind speed sustained at 16kn'
      ],
      plainHi: ['लहरों की ऊंचाई 2.6m'],
      variables: {},
      hourlyChart: [],
      sources: ['Open-Meteo Marine'],
      sourcesFailed: [],
      knownSources: 4,
      totalSources: 4,
      timestamp: DateTime.now(),
      staleness: StalenessInfo.fromDateTime(DateTime.now()),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: VerdictCard(advisory: fakeAdvisory),
        ),
      ),
    );

    // Verify Verdict
    expect(find.text('CAUTION ⚠'), findsOneWidget);

    // Verify English Headline
    expect(find.text('Moderate sea state (2.6 m waves).'), findsOneWidget);

    // Verify Hindi Headline
    expect(find.text('मध्यम समुद्री स्थिति।'), findsOneWidget);

    // Verify Plain Language Bullet
    expect(find.text('Wave height is 2.6m exceeding 2.5m threshold'), findsOneWidget);
  });
}
