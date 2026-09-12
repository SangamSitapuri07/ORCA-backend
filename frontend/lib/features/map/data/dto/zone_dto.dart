import '../../../../core/cache/staleness.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../domain/entities/zone_snapshot.dart';

/// DTO for /api/v1/zone. Optional measurements are intentionally nullable.
class ZoneDto {
  final double lat;
  final double lon;
  final String? zoneName;
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
  final Map<String, dynamic>? observationMetadataJson;
  final String? timestampStr;

  ZoneDto({
    required this.lat,
    required this.lon,
    this.zoneName,
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
    this.observationMetadataJson,
    this.timestampStr,
  });

  static double? _number(dynamic value) => value is num ? value.toDouble() : null;
  static List<String> _strings(dynamic value) => value is List
      ? value.map((item) => item.toString()).toList()
      : <String>[];

  factory ZoneDto.fromJson(Map<String, dynamic> json) {
    return ZoneDto(
      lat: _number(json['lat']) ?? (throw const FormatException('Zone response missing lat')),
      lon: _number(json['lon']) ?? (throw const FormatException('Zone response missing lon')),
      zoneName: json['zone_name'] as String?,
      offshoreDistKm: _number(json['offshore_dist_km']),
      depthM: _number(json['depth_m']),
      waveHeightM: _number(json['wave_height_m'] ?? json['wave_now_m']),
      swellPeriodS: _number(json['swell_period_s']),
      windSpeedKn: _number(json['wind_speed_kn']),
      windDirection: json['wind_direction'] as String?,
      seaTempC: _number(json['sea_temp_c'] ?? json['sst_mean'] ?? json['sst_max']),
      currentSpeedKn: _number(json['current_speed_kn']),
      currentDirection: json['current_direction'] as String?,
      chlorophyllMgM3: _number(json['chlorophyll_mg_m3'] ?? json['chlorophyll']),
      fishingEffortHours: _number(json['fishing_effort_hours'] ?? json['fishing_hours']),
      nearestHarbour: json['nearest_harbour'] as String?,
      nearestHarbourDistKm: _number(json['nearest_harbour_dist_km']),
      sources: _strings(json['sources']).isNotEmpty
          ? _strings(json['sources'])
          : _strings(json['data_sources_used']),
      sourcesFailed: _strings(json['sources_failed']).isNotEmpty
          ? _strings(json['sources_failed'])
          : _strings(json['data_sources_failed']),
      observationMetadataJson: json['observation_metadata'] is Map
          ? Map<String, dynamic>.from(json['observation_metadata'] as Map)
          : null,
      timestampStr: (json['fetched_at'] ?? json['timestamp']) as String?,
    );
  }

  DateTime? get parsedSourceTimestamp => DateFormatter.parseIso(timestampStr);

  DateTime get sourceTimestamp => parsedSourceTimestamp ??
      DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);

  ZoneSnapshot toEntity(StalenessInfo staleness) {
    const displayedObservationKeys = <String>{
      'wave_height_m',
      'wind_speed_kn',
      'sea_temp_c',
      'current_speed_kn',
      'chlorophyll_mg_m3',
      'fishing_effort_hours',
    };
    final observations = <String, ZoneObservationMetadata>{};
    observationMetadataJson?.forEach((key, raw) {
      if (!displayedObservationKeys.contains(key) || raw is! Map) return;
      final value = Map<String, dynamic>.from(raw);
      final observedAt = value['observed_at']?.toString();
      final observedFrom = value['observed_from']?.toString();
      final observedTo = value['observed_to']?.toString();
      final timeLabel = observedAt != null && observedAt.isNotEmpty
          ? observedAt
          : observedFrom != null && observedTo != null
              ? '$observedFrom to $observedTo'
              : 'Observation time unavailable';
      observations[key] = ZoneObservationMetadata(
        source: value['source']?.toString() ?? 'Source unavailable',
        timeLabel: timeLabel,
        statistic: value['statistic']?.toString(),
        note: value['note']?.toString(),
      );
    });

    return ZoneSnapshot(
      lat: lat,
      lon: lon,
      zoneName: zoneName ?? 'Ocean spot',
      offshoreDistKm: offshoreDistKm,
      depthM: depthM,
      waveHeightM: waveHeightM,
      swellPeriodS: swellPeriodS,
      windSpeedKn: windSpeedKn,
      windDirection: windDirection,
      seaTempC: seaTempC,
      currentSpeedKn: currentSpeedKn,
      currentDirection: currentDirection,
      chlorophyllMgM3: chlorophyllMgM3,
      fishingEffortHours: fishingEffortHours,
      nearestHarbour: nearestHarbour,
      nearestHarbourDistKm: nearestHarbourDistKm,
      sources: sources,
      sourcesFailed: sourcesFailed,
      observations: observations,
      timestamp: sourceTimestamp,
      staleness: staleness,
    );
  }
}

/// Legacy tile-catalog DTO retained for backward compatibility.
class LayerDto {
  final String id;
  final String name;
  final String? unit;
  final String? source;
  final String? tileUrl;
  final bool? enabled;

  LayerDto({
    required this.id,
    required this.name,
    this.unit,
    this.source,
    this.tileUrl,
    this.enabled,
  });

  factory LayerDto.fromJson(Map<String, dynamic> json) => LayerDto(
        id: json['id'] as String? ?? 'layer',
        name: json['name'] as String? ?? 'Layer',
        unit: json['unit'] as String?,
        source: json['source'] as String?,
        tileUrl: json['tile_url'] as String?,
        enabled: json['enabled'] as bool?,
      );

  MapLayerEntity toEntity() => MapLayerEntity(
        id: id,
        name: name,
        unit: unit ?? '',
        source: source ?? 'ORCA Box',
        tileUrl: tileUrl ?? '',
        isEnabled: enabled ?? false,
      );
}
