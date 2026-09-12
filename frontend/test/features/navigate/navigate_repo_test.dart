import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/features/navigate/data/dto/route_advisory_dto.dart';
import 'package:orca_app/features/navigate/data/dto/route_check_dto.dart';

void main() {
  group('Navigate DTO Tests', () {
    test('RouteCheckDto parses land collision & detour waypoint correctly', () {
      final jsonMap = {
        'ok': true,
        'detour': true,
        'land_hit': true,
        'reason': 'Direct rhumb line crosses coastal headland. Detour computed.',
        'distance_km': 42.6,
        'distance_nm': 23.0,
        'bearing_deg': 245.0,
        'legs': [
          [18.92, 72.83],
          [18.88, 72.78],
          [18.75, 72.55]
        ],
        'detour_waypoint': {
          'lat': 18.88,
          'lon': 72.78,
          'name': 'Colaba Offshore Detour WP1',
          'clearance_km': 3.2
        },
        'sources': ['GLOBE 1km Landmask']
      };

      final dto = RouteCheckDto.fromJson(jsonMap);
      final entity = dto.toEntity();

      expect(entity.ok, isTrue);
      expect(entity.detour, isTrue);
      expect(entity.landHit, isTrue);
      expect(entity.distanceKm, equals(42.6));
      expect(entity.legs.length, equals(3));
      expect(entity.detourWaypoint?.name, equals('Colaba Offshore Detour WP1'));
      expect(entity.detourWaypoint?.clearanceKm, equals(3.2));
    });

    test('RouteAdvisoryDto parses transit verdict and sampling points', () {
      final jsonMap = {
        'verdict': {
          'level': 'caution',
          'points_known': 4,
          'total': 4,
          'land_verified': true,
          'headline': 'Transit feasible with caution.'
        },
        'points': [
          {
            'sail_km': 0.0,
            'lat': 18.92,
            'lon': 72.83,
            'wave_m': 1.4,
            'wind_kn': 12.0,
            'state': 'good',
            'why': 'Sheltered harbour waters.'
          },
          {
            'sail_km': 42.6,
            'lat': 18.75,
            'lon': 72.55,
            'wave_m': 2.7,
            'wind_kn': 17.5,
            'state': 'caution',
            'why': 'Target zone: waves 2.7m.'
          }
        ],
        'safe_window_at_start': {
          'from': '06:00 IST',
          'to': '15:30 IST',
          'is_safe': true
        },
        'sources': ['Open-Meteo Marine', 'GLOBE 1km']
      };

      final dto = RouteAdvisoryDto.fromJson(jsonMap);
      final entity = dto.toEntity();

      expect(entity.level, equals('caution'));
      expect(entity.pointsKnown, equals(4));
      expect(entity.points.length, equals(2));
      expect(entity.points.last.waveM, equals(2.7));
      expect(entity.points.last.state, equals('caution'));
      expect(entity.safeWindowFrom, equals('06:00 IST'));
    });
  });
}
