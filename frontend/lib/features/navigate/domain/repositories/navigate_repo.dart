import '../../../../core/result/result.dart';
import '../entities/route_advisory.dart';
import '../entities/route_check.dart';

/// Contract for navigation route checks and transit verdicts (§10).
abstract class NavigateRepository {
  /// Verifies land clearance and computes detour.
  Future<Result<RouteCheckEntity>> checkRoute({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  });

  /// Evaluates transit safety advisory across entire route.
  Future<Result<RouteAdvisoryEntity>> getRouteAdvisory({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  });
}
