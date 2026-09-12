import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/config/api_paths.dart';

void main() {
  group('ApiPaths Tests', () {
    test('Canonical endpoints match the authoritative FastAPI backend', () {
      expect(ApiPaths.health, equals('/api/v1/health'));
      expect(ApiPaths.advisory, equals('/api/v1/advisory'));
      expect(ApiPaths.reason, equals('/api/v1/reason'));
      expect(ApiPaths.routeCheck, equals('/api/v1/route-check'));
      expect(ApiPaths.routeAdvisory, equals('/api/v1/route-advisory'));
      expect(ApiPaths.voyage, equals('/api/v1/voyage'));
      expect(ApiPaths.tileTemplate, equals('/api/v1/tiles/{z}/{x}/{y}.png'));
      expect(ApiPaths.liveStream, equals('/api/live/stream'));
    });
  });
}
