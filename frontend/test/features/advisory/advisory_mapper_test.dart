// ignore: unused_import
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/cache/staleness.dart';
import 'package:orca_app/features/advisory/data/dto/advisory_dto.dart';

void main() {
  group('AdvisoryDto & Entity Mapper Tests', () {
    test('Correctly maps full advisory payload to domain entity', () {
      final jsonMap = {
        'verdict': 'caution',
        'color': '#fbbf24',
        'headline': 'Moderate sea state with rising swell (2.6 m).',
        'headline_hi': 'मध्यम समुद्री स्थिति।',
        'plain_en': ['Wave height is 2.6m'],
        'plain_hi': ['लहरों की ऊंचाई 2.6m है'],
        'safe_window': {
          'from': '06:00 IST',
          'to': '15:30 IST',
          'is_safe': true,
          'hours_remaining': 9.5
        },
        'variables': {
          'wave_height': {
            'value': 2.6,
            'unit': 'm',
            'threshold': 2.5,
            'status': 'caution',
            'source': 'Open-Meteo',
            'time': '11:00 IST'
          }
        },
        'hourly_chart': [
          {'hour': '06:00', 'wave_m': 1.4, 'wind_kn': 12.0, 'state': 'good'}
        ],
        'sources': ['Open-Meteo Marine', 'NOAA CoastWatch'],
        'data_coverage': {
          'known': 4,
          'total': 5,
          'sources_failed': ['ESA OC-CCI (no valid pixels)']
        },
        'timestamp': '2026-09-12T08:30:00Z'
      };

      final dto = AdvisoryDto.fromJson(jsonMap);
      final staleness = StalenessInfo.fromDateTime(DateTime.now());
      final entity = dto.toEntity(staleness);

      expect(entity.verdict, equals('caution'));
      expect(entity.headline, contains('Moderate sea state'));
      expect(entity.headlineHi, equals('मध्यम समुद्री स्थिति।'));
      expect(entity.safeWindow?.isSafe, isTrue);
      expect(entity.safeWindow?.from, equals('06:00 IST'));
      expect(entity.variables['wave_height']?.value, equals(2.6));
      expect(entity.variables['wave_height']?.status, equals('caution'));
      expect(entity.hourlyChart.length, equals(1));
      expect(entity.sources.length, equals(2));
      expect(entity.sourcesFailed.first, contains('no valid pixels'));
      expect(entity.knownSources, equals(4));
    });

    test('formats backend observation windows without replacing them with receipt time', () {
      final dto = AdvisoryDto.fromJson({
        'verdict': 'unknown',
        'variable_details': {
          'sea_surface_temp': {
            'value': 28.4,
            'unit': '°C',
            'status': 'context_only',
            'source': 'Open-Meteo Marine API',
            'observed_from': '2026-08-01',
            'observed_to': '2026-08-31',
            'retrieved_at': '2026-09-12T08:30:00Z',
          },
        },
      });

      final entity = dto.toEntity(
        StalenessInfo.fromDateTime(DateTime.now()),
      );

      expect(entity.variables['sea_surface_temp']?.time, '2026-08-01 to 2026-08-31');
      expect(entity.variables['sea_surface_temp']?.source, 'Open-Meteo Marine API');
    });

    test('does not calculate hourly safety state when backend omits it', () {
      final dto = AdvisoryDto.fromJson({
        'verdict': 'unknown',
        'hourly_chart': {
          'labels': ['09-12T06:00'],
          'wave_m': [5.0],
          'wind_kn': [40.0],
        },
      });

      final entity = dto.toEntity(
        StalenessInfo.fromDateTime(DateTime.now()),
      );

      expect(entity.hourlyChart.single.state, 'unknown');
    });

    test('retains backend-owned hourly safety state', () {
      final dto = AdvisoryDto.fromJson({
        'verdict': 'caution',
        'hourly_chart': {
          'labels': ['09-12T06:00'],
          'wave_m': [1.0],
          'wind_kn': [10.0],
          'state': ['caution'],
        },
      });

      final entity = dto.toEntity(
        StalenessInfo.fromDateTime(DateTime.now()),
      );

      expect(entity.hourlyChart.single.state, 'caution');
    });

    test('Tolerates missing optional fields without crashing (§4)', () {
      final jsonMap = <String, dynamic>{
        'verdict': 'go',
      };

      final dto = AdvisoryDto.fromJson(jsonMap);
      final staleness = StalenessInfo.fromDateTime(DateTime.now());
      final entity = dto.toEntity(staleness);

      expect(entity.verdict, equals('go'));
      expect(entity.plainEn, isEmpty);
      expect(entity.hourlyChart, isEmpty);
      expect(entity.safeWindow, isNull);
    });
  });
}
