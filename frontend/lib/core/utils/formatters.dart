/// Physical units and numbers formatting for high-readability displays.
class Formatters {
  /// Wave height in meters with unit, e.g. "2.6 m".
  static String waveHeight(double? meters) {
    if (meters == null) return '--';
    return '${meters.toStringAsFixed(1)} m';
  }

  /// Wind speed in knots, e.g. "16.2 kn".
  static String windKnots(double? knots) {
    if (knots == null) return '--';
    return '${knots.toStringAsFixed(1)} kn';
  }

  /// Temperature in Celsius, e.g. "28.4 °C".
  static String temperature(double? celsius) {
    if (celsius == null) return '--';
    return '${celsius.toStringAsFixed(1)} °C';
  }

  /// Current velocity in knots with direction, e.g. "1.4 kn SSW".
  static String current(double? knots, [String? direction]) {
    if (knots == null) return '--';
    if (direction != null && direction.isNotEmpty) {
      return '${knots.toStringAsFixed(1)} kn $direction';
    }
    return '${knots.toStringAsFixed(1)} kn';
  }

  /// Chlorophyll in mg/m³, e.g. "0.82 mg/m³".
  static String chlorophyll(double? value) {
    if (value == null) return '--';
    return '${value.toStringAsFixed(2)} mg/m³';
  }

  /// Fishing effort in hours, e.g. "14.2 hrs".
  static String fishingEffort(double? hours) {
    if (hours == null) return '--';
    return '${hours.toStringAsFixed(1)} hrs';
  }

  /// Distance in km and nautical miles, e.g. "42.6 km (23.0 NM)".
  static String distanceDual(double km) {
    final nm = km * 0.539957;
    return '${km.toStringAsFixed(1)} km (${nm.toStringAsFixed(1)} NM)';
  }
}
