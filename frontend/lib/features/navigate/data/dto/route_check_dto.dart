import '../../domain/entities/route_check.dart';

class RouteCheckDto {
  final bool? ok;
  final bool detour;
  final bool landHit;
  final String reason;
  final double distanceKm;
  final double distanceNm;
  final double bearingDeg;
  final List<dynamic> legsList;
  final Map<String, dynamic>? detourWpJson;
  final List<String> sources;

  RouteCheckDto({
    required this.ok,
    required this.detour,
    required this.landHit,
    required this.reason,
    required this.distanceKm,
    required this.distanceNm,
    required this.bearingDeg,
    required this.legsList,
    this.detourWpJson,
    required this.sources,
  });

  static double _requiredNumber(Map<String, dynamic> json, String key) {
    final value = json[key];
    if (value is num) return value.toDouble();
    throw FormatException('Route response missing $key');
  }

  static List<String> _strings(dynamic value) => value is List
      ? value.map((item) => item.toString()).toList()
      : <String>[];

  factory RouteCheckDto.fromJson(Map<String, dynamic> json) {
    final legs = json['legs'] is List ? json['legs'] as List : const [];
    Map<String, dynamic>? waypoint;
    if (json['detour_waypoint'] is Map) {
      waypoint = Map<String, dynamic>.from(json['detour_waypoint'] as Map);
    } else if (json['waypoints'] is List && (json['waypoints'] as List).isNotEmpty) {
      final raw = (json['waypoints'] as List).first;
      if (raw is List && raw.length >= 2) {
        waypoint = <String, dynamic>{'lat': raw[0], 'lon': raw[1]};
      }
    } else if (json['detour'] == true && legs.length > 2 && legs[1] is List) {
      final raw = legs[1] as List;
      if (raw.length >= 2) waypoint = <String, dynamic>{'lat': raw[0], 'lon': raw[1]};
    }

    return RouteCheckDto(
      ok: json['ok'] as bool?,
      detour: json['detour'] == true,
      landHit: json['land_hit'] != null && json['land_hit'] != false,
      reason: json['reason'] as String? ?? 'Route verification reason unavailable.',
      distanceKm: _requiredNumber(json, 'distance_km'),
      distanceNm: _requiredNumber(json, 'distance_nm'),
      bearingDeg: _requiredNumber(json, 'bearing_deg'),
      legsList: legs,
      detourWpJson: waypoint,
      sources: _strings(json['sources']),
    );
  }

  RouteCheckEntity toEntity() {
    final parsedLegs = <List<double>>[];
    for (final raw in legsList) {
      if (raw is List && raw.length >= 2 && raw[0] is num && raw[1] is num) {
        parsedLegs.add(<double>[(raw[0] as num).toDouble(), (raw[1] as num).toDouble()]);
      }
    }

    DetourWaypoint? waypoint;
    final rawWaypoint = detourWpJson;
    if (rawWaypoint != null && rawWaypoint['lat'] is num && rawWaypoint['lon'] is num) {
      waypoint = DetourWaypoint(
        lat: (rawWaypoint['lat'] as num).toDouble(),
        lon: (rawWaypoint['lon'] as num).toDouble(),
        name: rawWaypoint['name'] as String? ?? 'Computed detour waypoint',
        clearanceKm: (rawWaypoint['clearance_km'] as num?)?.toDouble(),
      );
    }

    return RouteCheckEntity(
      ok: ok,
      detour: detour,
      landHit: landHit,
      reason: reason,
      distanceKm: distanceKm,
      distanceNm: distanceNm,
      bearingDeg: bearingDeg,
      legs: parsedLegs,
      detourWaypoint: waypoint,
      sources: sources,
    );
  }
}

class RouteAdvisoryDto {
  final Map<String, dynamic>? verdictJson;
  final List<dynamic> pointsList;
  final Map<String, dynamic>? safeWindowJson;
  final List<String> sources;
  final List<String> sourcesFailed;

  RouteAdvisoryDto({
    this.verdictJson,
    required this.pointsList,
    this.safeWindowJson,
    required this.sources,
    required this.sourcesFailed,
  });

  factory RouteAdvisoryDto.fromJson(Map<String, dynamic> json) {
    return RouteAdvisoryDto(
      verdictJson: json['verdict'] is Map
          ? Map<String, dynamic>.from(json['verdict'] as Map)
          : null,
      pointsList: json['points'] is List ? json['points'] as List : const [],
      safeWindowJson: json['safe_window_at_start'] is Map
          ? Map<String, dynamic>.from(json['safe_window_at_start'] as Map)
          : null,
      sources: RouteCheckDto._strings(json['sources']).isNotEmpty
          ? RouteCheckDto._strings(json['sources'])
          : RouteCheckDto._strings(json['sources_used']),
      sourcesFailed: RouteCheckDto._strings(json['sources_failed']),
    );
  }

  RouteAdvisoryEntity toEntity() {
    final parsedPoints = <TransitPoint>[];
    for (final raw in pointsList) {
      if (raw is! Map) continue;
      final point = Map<String, dynamic>.from(raw);
      if (point['sail_km'] is! num || point['lat'] is! num || point['lon'] is! num) continue;
      parsedPoints.add(TransitPoint(
        sailKm: (point['sail_km'] as num).toDouble(),
        lat: (point['lat'] as num).toDouble(),
        lon: (point['lon'] as num).toDouble(),
        waveM: (point['wave_m'] as num?)?.toDouble(),
        windKn: (point['wind_kn'] as num?)?.toDouble(),
        state: point['state'] as String? ?? 'unknown',
        why: (point['why'] ?? point['note']) as String? ?? 'No point explanation returned.',
      ));
    }

    final verdict = verdictJson;
    final window = safeWindowJson;
    return RouteAdvisoryEntity(
      level: verdict?['level'] as String? ?? 'unknown',
      pointsKnown: verdict?['points_known'] as int? ?? 0,
      totalPoints: (verdict?['points_total'] ?? verdict?['total']) as int? ?? pointsList.length,
      landVerified: verdict?['land_verified'] as bool?,
      headline: verdict?['headline'] as String? ?? 'Route verdict explanation unavailable.',
      points: parsedPoints,
      safeWindowFrom: (window?['from_utc'] ?? window?['from']) as String?,
      safeWindowTo: (window?['to_utc'] ?? window?['to']) as String?,
      isSafeStart: window?['found'] as bool? ?? window?['is_safe'] as bool? ?? false,
      sources: sources,
      sourcesFailed: sourcesFailed,
    );
  }
}
