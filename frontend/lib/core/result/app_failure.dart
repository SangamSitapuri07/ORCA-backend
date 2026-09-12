/// Sealed class representing typed app failures (§10).
sealed class AppFailure {
  final String message;
  const AppFailure(this.message);

  /// Offline failure.
  const factory AppFailure.offline([String message]) = OfflineFailure;

  /// Server down / connection refused failure.
  const factory AppFailure.serverDown([String message]) = ServerDownFailure;

  /// Specific upstream source down (e.g. INCOIS / MOSDAC).
  const factory AppFailure.sourceDown({
    required String source,
    required String reason,
  }) = SourceDownFailure;

  /// Stale cached data returned when live fetch failed.
  const factory AppFailure.stale({
    required Duration age,
    required String message,
  }) = StaleFailure;

  /// Bad or malformed JSON payload from backend.
  const factory AppFailure.badPayload([String message]) = BadPayloadFailure;

  /// Timeout failure.
  const factory AppFailure.timeout([String message]) = TimeoutFailure;

  /// Generic/unknown failure.
  const factory AppFailure.unknown([String message]) = UnknownFailure;

  @override
  String toString() => message;
}

final class OfflineFailure extends AppFailure {
  const OfflineFailure([super.message = 'Device is offline. Showing cached data if available.']);
}

final class ServerDownFailure extends AppFailure {
  const ServerDownFailure([super.message = 'ORCA Box server is unreachable. Check network/IP.']);
}

final class SourceDownFailure extends AppFailure {
  final String source;
  final String reason;
  const SourceDownFailure({required this.source, required this.reason})
      : super('Source $source unavailable: $reason');
}

final class StaleFailure extends AppFailure {
  final Duration age;
  const StaleFailure({required this.age, required String message}) : super(message);
}

final class BadPayloadFailure extends AppFailure {
  const BadPayloadFailure([super.message = 'Received invalid response structure from backend.']);
}

final class TimeoutFailure extends AppFailure {
  const TimeoutFailure([super.message = 'Request timed out after 15 seconds.']);
}

final class UnknownFailure extends AppFailure {
  const UnknownFailure([super.message = 'An unexpected error occurred.']);
}
