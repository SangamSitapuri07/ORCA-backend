import '../../../../core/result/result.dart';
import '../entities/route_advisory.dart';
import '../entities/route_check.dart';
import '../repositories/navigate_repo.dart';

/// Usecase for route check & transit verdict evaluation (§10).
class GetRouteAdvisoryUseCase {
  final NavigateRepository _repository;

  GetRouteAdvisoryUseCase(this._repository);

  Future<Result<RouteCheckEntity>> checkRoute({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  }) {
    return _repository.checkRoute(
      fromLat: fromLat,
      fromLon: fromLon,
      toLat: toLat,
      toLon: toLon,
    );
  }

  Future<Result<RouteAdvisoryEntity>> getRouteAdvisory({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  }) {
    return _repository.getRouteAdvisory(
      fromLat: fromLat,
      fromLon: fromLon,
      toLat: toLat,
      toLon: toLon,
    );
  }
}
