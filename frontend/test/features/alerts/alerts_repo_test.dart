import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/features/alerts/data/dto/alert_dto.dart';

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
  });
}
