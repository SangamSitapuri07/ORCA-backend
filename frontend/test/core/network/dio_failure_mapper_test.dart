import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/network/dio_failure_mapper.dart';
import 'package:orca_app/core/result/app_failure.dart';

void main() {
  test('reports measured HTTP status without calling the server down', () {
    final request = RequestOptions(path: '/api/v1/alerts');
    final failure = mapDioFailure(DioException(
      requestOptions: request,
      response: Response<void>(
        requestOptions: request,
        statusCode: 503,
        statusMessage: 'Service Unavailable',
      ),
      type: DioExceptionType.badResponse,
    ));

    expect(failure, isA<UnknownFailure>());
    expect(failure.message, contains('HTTP 503'));
    expect(failure.message.toLowerCase(), isNot(contains('down')));
  });

  test('distinguishes response timeout from connection failure', () {
    final request = RequestOptions(path: '/api/v1/reason');
    final timeout = mapDioFailure(DioException(
      requestOptions: request,
      type: DioExceptionType.receiveTimeout,
    ));
    final connection = mapDioFailure(DioException(
      requestOptions: request,
      type: DioExceptionType.connectionError,
      message: 'Socket closed',
    ));

    expect(timeout, isA<TimeoutFailure>());
    expect(timeout.message, contains('response timed out'));
    expect(connection, isA<ServerDownFailure>());
    expect(connection.message, contains('Could not connect'));
  });
}
