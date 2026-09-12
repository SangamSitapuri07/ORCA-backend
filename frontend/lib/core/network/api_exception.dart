import '../result/app_failure.dart';

/// Exception thrown on network and API client errors.
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final dynamic data;
  final AppFailure failure;

  const ApiException({
    required this.message,
    this.statusCode,
    this.data,
    required this.failure,
  });

  @override
  String toString() => 'ApiException(status: $statusCode, message: $message)';
}
