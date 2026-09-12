import 'package:dio/dio.dart';
import '../../../../core/config/api_paths.dart';
import '../dto/route_advisory_dto.dart';
import '../dto/route_check_dto.dart';

/// Remote datasource for Route navigation endpoints (/api/v1/route-check, /api/v1/route-advisory).
class NavigateRemoteDataSource {
  final Dio _dio;

  NavigateRemoteDataSource(this._dio);

  /// Performs 2km GLOBE land mask collision check & detour computation.
  Future<RouteCheckDto> checkRoute({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      ApiPaths.routeCheck,
      queryParameters: <String, dynamic>{
        'from_lat': fromLat,
        'from_lon': fromLon,
        'to_lat': toLat,
        'to_lon': toLon,
      },
    );

    if (response.data == null) {
      throw Exception('Empty response from route-check');
    }

    return RouteCheckDto.fromJson(response.data!);
  }

  /// Evaluates full transit safety verdict across 30km samples.
  Future<RouteAdvisoryDto> getRouteAdvisory({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      ApiPaths.routeAdvisory,
      queryParameters: <String, dynamic>{
        'from_lat': fromLat,
        'from_lon': fromLon,
        'to_lat': toLat,
        'to_lon': toLon,
      },
    );

    if (response.data == null) {
      throw Exception('Empty response from route-advisory');
    }

    return RouteAdvisoryDto.fromJson(response.data!);
  }
}
