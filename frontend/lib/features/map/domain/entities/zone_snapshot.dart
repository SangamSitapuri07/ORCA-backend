import '../../../../core/cache/staleness.dart';

class ZoneObservationMetadata {
  final String source;
  final String timeLabel;
  final String? statistic;
  final String? note;

  const ZoneObservationMetadata({
    required this.source,
    required this.timeLabel,
    this.statistic,
    this.note,
  });
}

/// Single ocean spot snapshot. Missing provider measurements stay nullable.
class ZoneSnapshot {
  final double lat;
  final double lon;
  final String zoneName;
  final double? offshoreDistKm;
  final double? depthM;
  final double? waveHeightM;
  final double? swellPeriodS;
  final double? windSpeedKn;
  final String? windDirection;
  final double? seaTempC;
  final double? currentSpeedKn;
  final String? currentDirection;
  final double? chlorophyllMgM3;
  final double? fishingEffortHours;
  final String? nearestHarbour;
  final double? nearestHarbourDistKm;
  final List<String> sources;
  final List<String> sourcesFailed;
  final Map<String, ZoneObservationMetadata> observations;
  final DateTime timestamp;
  final StalenessInfo staleness;

  const ZoneSnapshot({
    required this.lat,
    required this.lon,
    required this.zoneName,
    this.offshoreDistKm,
    this.depthM,
    this.waveHeightM,
    this.swellPeriodS,
    this.windSpeedKn,
    this.windDirection,
    this.seaTempC,
    this.currentSpeedKn,
    this.currentDirection,
    this.chlorophyllMgM3,
    this.fishingEffortHours,
    this.nearestHarbour,
    this.nearestHarbourDistKm,
    required this.sources,
    required this.sourcesFailed,
    this.observations = const <String, ZoneObservationMetadata>{},
    required this.timestamp,
    required this.staleness,
  });
}

class GeoCoordinate {
  final double lat;
  final double lon;

  const GeoCoordinate(this.lat, this.lon);
}

/// One normalized geometry returned by the ORCA Box GeoJSON endpoint.
class GeoFeatureEntity {
  final String layer;
  final String name;
  final String geometryType;
  final GeoCoordinate? point;
  final List<List<GeoCoordinate>> paths;
  final Map<String, dynamic> properties;

  const GeoFeatureEntity({
    required this.layer,
    required this.name,
    required this.geometryType,
    this.point,
    this.paths = const <List<GeoCoordinate>>[],
    this.properties = const <String, dynamic>{},
  });
}

class GeoLayerCollection {
  final List<GeoFeatureEntity> features;
  final List<String> sources;
  final List<String> errors;
  final DateTime generatedAt;

  const GeoLayerCollection({
    required this.features,
    required this.sources,
    required this.errors,
    required this.generatedAt,
  });
}

/// User-selectable backend GeoJSON layer.
class MapLayerEntity {
  final String id;
  final String name;
  final String unit;
  final String source;
  final String tileUrl;
  final bool isEnabled;

  const MapLayerEntity({
    required this.id,
    required this.name,
    required this.unit,
    required this.source,
    required this.tileUrl,
    this.isEnabled = false,
  });

  MapLayerEntity copyWith({bool? isEnabled}) {
    return MapLayerEntity(
      id: id,
      name: name,
      unit: unit,
      source: source,
      tileUrl: tileUrl,
      isEnabled: isEnabled ?? this.isEnabled,
    );
  }
}
