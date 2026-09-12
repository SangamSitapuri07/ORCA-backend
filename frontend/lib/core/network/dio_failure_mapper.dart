import 'package:dio/dio.dart';
import '../result/app_failure.dart';

/// Converts measured Dio outcomes into user-facing failures without guessing
/// that an HTTP error, timeout, or TLS problem means the server is "down".
AppFailure mapDioFailure(DioException error) {
  switch (error.type) {
    case DioExceptionType.connectionTimeout:
      return const AppFailure.timeout('Connection to ORCA Box timed out.');
    case DioExceptionType.sendTimeout:
      return const AppFailure.timeout('Sending the ORCA Box request timed out.');
    case DioExceptionType.receiveTimeout:
      return const AppFailure.timeout('Waiting for the ORCA Box response timed out.');
    case DioExceptionType.connectionError:
      return AppFailure.serverDown(
        _withDetail('Could not connect to ORCA Box.', error.message),
      );
    case DioExceptionType.badCertificate:
      return const AppFailure.unknown(
        'ORCA Box TLS certificate validation failed.',
      );
    case DioExceptionType.badResponse:
      final status = error.response?.statusCode;
      final reason = error.response?.statusMessage;
      final measured = status == null
          ? 'ORCA Box returned an HTTP error.'
          : 'ORCA Box returned HTTP $status.';
      return AppFailure.unknown(_withDetail(measured, reason));
    case DioExceptionType.cancel:
      return const AppFailure.unknown('ORCA Box request was cancelled.');
    case DioExceptionType.unknown:
      return AppFailure.unknown(
        _withDetail('ORCA Box request failed.', error.message),
      );
  }
}

String _withDetail(String message, String? detail) {
  final clean = detail?.trim();
  if (clean == null || clean.isEmpty || message.contains(clean)) return message;
  return '$message $clean';
}
