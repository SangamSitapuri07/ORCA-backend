import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/features/alerts/data/dto/alert_dto.dart';
import 'package:orca_app/features/alerts/data/dto/alerts_snapshot_dto.dart';

void main() {
  group('Alerts DTO Tests', () {
    test('Parses active alerts correctly', () {
      final jsonMap = {
        'id': 'alt-2026-09-01',
        'severity': 'caution',
        'title': 'Rising Swell Advisory',
        'title_hi': 'लहरों में वृद्धि की चेतावनी',
        'message': 'Wave heights forecast to reach 2.8m–3.2m.',
        'source': 'INCOIS OSF',
        'issued_at': '2026-09-12T07:00:00Z',
        'affected_area': 'North Maharashtra Coast',
        'is_active': true
      };

      final dto = AlertDto.fromJson(jsonMap);
      final entity = dto.toEntity();

      expect(entity.id, equals('alt-2026-09-01'));
      expect(entity.severity, equals('caution'));
      expect(entity.title, equals('Rising Swell Advisory'));
      expect(entity.titleHi, equals('लहरों में वृद्धि की चेतावनी'));
      expect(entity.source, equals('INCOIS OSF'));
      expect(entity.isActive, isTrue);
    });

    test('Missing evaluation evidence is incomplete, not an all-clear', () {
      final snapshot = AlertsSnapshotDto.fromJson({
        'alerts': <dynamic>[],
      }).toEntity();

      expect(snapshot.checkIncomplete, isTrue);
      expect(snapshot.hasEvaluationEvidence, isFalse);
    });

    test('Checked time without per-source evidence remains incomplete', () {
      final snapshot = AlertsSnapshotDto.fromJson({
        'alerts': <dynamic>[],
        'evaluation': {
          'checked_at': '2026-09-12T07:30:00Z',
        },
      }).toEntity();

      expect(snapshot.hasEvaluationEvidence, isFalse);
      expect(snapshot.checkIncomplete, isTrue);
    });

    test('Completed source plus checked time can report no active alerts', () {
      final snapshot = AlertsSnapshotDto.fromJson({
        'alerts': <dynamic>[],
        'evaluation': {
          'sources_used': <String>['Open-Meteo forecast'],
          'sources_failed': <String>[],
          'checked_at': '2026-09-12T07:30:00Z',
        },
      }).toEntity();

      expect(snapshot.hasEvaluationEvidence, isTrue);
      expect(snapshot.checkIncomplete, isFalse);
    });

    test('Retains alert-evaluation failures and checked time', () {
      final dto = AlertsSnapshotDto.fromJson({
        'alerts': <dynamic>[],
        'evaluation': {
          'sources_used': <String>[],
          'sources_failed': <String>[
            'Open-Meteo forecast: timeout',
            'JTWC: connection failed',
          ],
          'checked_at': '2026-09-12T07:30:00Z',
        },
      });
      final snapshot = dto.toEntity();

      expect(snapshot.alerts, isEmpty);
      expect(snapshot.checkIncomplete, isTrue);
      expect(snapshot.sourcesFailed, hasLength(2));
      expect(snapshot.checkedAt, DateTime.parse('2026-09-12T07:30:00Z'));
    });
  });
}
