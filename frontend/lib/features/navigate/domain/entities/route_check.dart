class DetourWaypoint {
  final double lat;
  final double lon;
  final String name;
  final double? clearanceKm;

  const DetourWaypoint({
    required this.lat,
    required this.lon,
    required this.name,
    this.clearanceKm,
  });
}

/// ``ok`` is nullable: null means the land mask could not verify the route.
class RouteCheckEntity {
  final bool? ok;
  final bool detour;
  final bool landHit;
  final String reason;
  final double distanceKm;
  final double distanceNm;
  final double bearingDeg;
  final List<List<double>> legs;
  final DetourWaypoint? detourWaypoint;
  final List<String> sources;

  const RouteCheckEntity({
    required this.ok,
    required this.detour,
    required this.landHit,
    required this.reason,
    required this.distanceKm,
    required this.distanceNm,
    required this.bearingDeg,
    required this.legs,
    this.detourWaypoint,
    required this.sources,
  });
}

class TransitPoint {
  final double sailKm;
  final double lat;
  final double lon;
  final double? waveM;
  final double? windKn;
  final String state;
  final String why;

  const TransitPoint({
    required this.sailKm,
    required this.lat,
    required this.lon,
    this.waveM,
    this.windKn,
    required this.state,
    required this.why,
  });
}

class RouteAdvisoryEntity {
  final String level;
  final int pointsKnown;
  final int totalPoints;
  final bool? landVerified;
  final String headline;
  final List<TransitPoint> points;
  final String? safeWindowFrom;
  final String? safeWindowTo;
  final bool isSafeStart;
  final List<String> sources;
  final List<String> sourcesFailed;

  const RouteAdvisoryEntity({
    required this.level,
    required this.pointsKnown,
    required this.totalPoints,
    required this.landVerified,
    required this.headline,
    required this.points,
    this.safeWindowFrom,
    this.safeWindowTo,
    required this.isSafeStart,
    required this.sources,
    this.sourcesFailed = const <String>[],
  });
}
