import '../../../../core/result/result.dart';

import '../entities/zone_snapshot.dart';
import '../repositories/map_repo.dart';

/// Usecase for probing a specific coordinate spot (§10).
class GetZoneSnapshotUseCase {
  final MapRepository _repository;

  GetZoneSnapshotUseCase(this._repository);

  Future<Result<ZoneSnapshot>> execute({
    required double lat,
    required double lon,
  }) {
    return _repository.probeZone(lat: lat, lon: lon);
  }

  Future<Result<GeoLayerCollection>> getGeoLayers() {
    return _repository.getGeoLayers();
  }
}
