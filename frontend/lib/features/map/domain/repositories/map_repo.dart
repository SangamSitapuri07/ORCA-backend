import '../../../../core/result/result.dart';

import '../entities/zone_snapshot.dart';

/// Contract for map and GIS probe access (§10).
abstract class MapRepository {
  /// Probes ocean point conditions at [lat], [lon].
  Future<Result<ZoneSnapshot>> probeZone({
    required double lat,
    required double lon,
  });

  /// Retrieves real GeoJSON overlays from the ORCA Box.
  Future<Result<GeoLayerCollection>> getGeoLayers();
}
