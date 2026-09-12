import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../config/app_config.dart';
import '../cache/cache_service.dart';

/// State provider storing user-configured ORCA box base URL.
final baseUrlProvider = StateProvider<String>((ref) {
  return ref.watch(cacheServiceProvider).get('settings.base_url')?.data['value'] as String? ??
      AppConfig.defaultBaseUrl;
});

/// Shared Dio client provider configured with 15s timeout & retry-once interceptor.
final dioProvider = Provider<Dio>((ref) {
  final baseUrl = ref.watch(baseUrlProvider);
  final dio = Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: AppConfig.connectTimeout,
      receiveTimeout: AppConfig.receiveTimeout,
      sendTimeout: AppConfig.sendTimeout,
      headers: <String, dynamic>{
        'Accept': 'application/json',
        'User-Agent': 'ORCA-Flutter-Client/1.0 (SIH26176)',
      },
    ),
  );

  // Retry once on a transient connection failure. Canonical paths are owned by
  // ApiPaths at repository call sites; this client never guesses legacy routes.
  dio.interceptors.add(
    InterceptorsWrapper(
      onError: (DioException err, ErrorInterceptorHandler handler) async {
        debugPrint('[Dio Error] ${err.requestOptions.path} -> ${err.message}');

        // Retry once on connection/timeout error
        final isTimeout = err.type == DioExceptionType.connectionTimeout ||
            err.type == DioExceptionType.receiveTimeout ||
            err.type == DioExceptionType.connectionError;

        final hasRetried = err.requestOptions.extra['has_retried'] == true;
        if (isTimeout && !hasRetried) {
          err.requestOptions.extra['has_retried'] = true;
          try {
            debugPrint('[Dio Retry] Retrying request: ${err.requestOptions.path}');
            final response = await dio.fetch<dynamic>(err.requestOptions);
            return handler.resolve(response);
          } catch (retryError) {
            if (retryError is DioException) {
              return handler.next(retryError);
            }
          }
        }

        return handler.next(err);
      },
    ),
  );

  return dio;
});
