import 'dart:math' as math;

/// Geographic calculations and coordinate helpers.
class GeoUtils {
  /// Converts degrees to radians.
  static double _degToRad(double deg) => deg * (math.pi / 180.0);

  /// Converts radians to degrees.
  static double _radToDeg(double rad) => rad * (180.0 / math.pi);

  /// Calculates Great Circle / Haversine distance in kilometers between two points.
  static double distanceKm(double lat1, double lon1, double lat2, double lon2) {
    const r = 6371.0; // Earth radius in km
    final dLat = _degToRad(lat2 - lat1);
    final dLon = _degToRad(lon2 - lon1);

    final a = math.sin(dLat / 2) * math.sin(dLat / 2) +
        math.cos(_degToRad(lat1)) * math.cos(_degToRad(lat2)) * math.sin(dLon / 2) * math.sin(dLon / 2);
    final c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));
    return r * c;
  }

  /// Converts kilometers to Nautical Miles.
  static double kmToNauticalMiles(double km) => km * 0.539957;

  /// Calculates initial bearing in degrees (0-360) from point 1 to point 2.
  static double bearingDegrees(double lat1, double lon1, double lat2, double lon2) {
    final phi1 = _degToRad(lat1);
    final phi2 = _degToRad(lat2);
    final deltaLambda = _degToRad(lon2 - lon1);

    final y = math.sin(deltaLambda) * math.cos(phi2);
    final x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(deltaLambda);
    final theta = math.atan2(y, x);
    final bearing = (_radToDeg(theta) + 360) % 360;
    return bearing;
  }

  /// Formats coordinate nicely, e.g. "18.92°N, 72.83°E".
  static String formatCoordinate(double lat, double lon) {
    final latDir = lat >= 0 ? 'N' : 'S';
    final lonDir = lon >= 0 ? 'E' : 'W';
    return '${lat.abs().toStringAsFixed(2)}°$latDir, ${lon.abs().toStringAsFixed(2)}°$lonDir';
  }
}
