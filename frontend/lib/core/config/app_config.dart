/// Application configuration and environment constants.
class AppConfig {
  /// Inject the ORCA Box deployment URL at build time. An empty value is an
  /// explicit unconfigured state; production APKs never embed a machine or LAN
  /// address.
  static const String defaultBaseUrl = String.fromEnvironment(
    'ORCA_API_BASE_URL',
    defaultValue: '',
  );

  /// Initial map centre only; never treated as a measured device location.
  static const double defaultLat = 18.92;
  static const double defaultLon = 72.83;

  /// Timeouts for Dio network requests.
  static const Duration connectTimeout = Duration(seconds: 15);
  // Cold public-provider fetches are bounded by the ORCA Box at 110s.
  static const Duration receiveTimeout = Duration(seconds: 125);
  static const Duration sendTimeout = Duration(seconds: 15);

  /// Default cache TTLs.
  static const Duration advisoryTtl = Duration(minutes: 30);
  static const Duration healthTtl = Duration(minutes: 5);
}
