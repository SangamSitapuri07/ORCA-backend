import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/cache/staleness.dart';
import 'package:orca_app/core/theme/verdict_colors.dart';

void main() {
  group('Staleness Tests', () {
    test('Timestamp within 30 minutes evaluates to fresh', () {
      final now = DateTime.now().subtract(const Duration(minutes: 10));
      final staleness = StalenessInfo.fromDateTime(now);
      expect(staleness.state, equals(StalenessState.fresh));
      expect(staleness.color, equals(VerdictColors.go));
      expect(staleness.label, contains('Fresh'));
    });

    test('Timestamp between 30m and 3h evaluates to recent', () {
      final recentTime = DateTime.now().subtract(const Duration(minutes: 90));
      final staleness = StalenessInfo.fromDateTime(recentTime);
      expect(staleness.state, equals(StalenessState.recent));
      expect(staleness.color, equals(VerdictColors.caution));
    });

    test('Timestamp older than 3 hours evaluates to stale', () {
      final oldTime = DateTime.now().subtract(const Duration(hours: 6));
      final staleness = StalenessInfo.fromDateTime(oldTime);
      expect(staleness.state, equals(StalenessState.stale));
      expect(staleness.color, equals(VerdictColors.stale));
      expect(staleness.label, contains('6h ago'));
    });
  });
}
