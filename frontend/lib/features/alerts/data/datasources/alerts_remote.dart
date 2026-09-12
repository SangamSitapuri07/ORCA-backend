import 'package:dio/dio.dart';
import '../../../../core/config/api_paths.dart';
import '../dto/alert_dto.dart';

/// Remote datasource for live and explicitly simulated ORCA Box alerts.
class AlertsRemoteDataSource {
  final Dio _dio;

  AlertsRemoteDataSource(this._dio);

  Future<List<AlertDto>> getActiveAlerts({
    required double lat,
    required double lon,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      ApiPaths.alerts,
      queryParameters: <String, dynamic>{'lat': lat, 'lon': lon},
    );
    final raw = response.data?['alerts'];
    if (raw is! List) return <AlertDto>[];
    return raw
        .whereType<Map>()
        .map((item) => AlertDto.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<AlertDto> simulateAlert({
    required double lat,
    required double lon,
  }) async {
    final response = await _dio.post<Map<String, dynamic>>(
      ApiPaths.alertsSimulate,
      data: <String, dynamic>{'type': 'cyclone', 'lat': lat, 'lon': lon},
    );
    final created = response.data?['created'];
    if (created is! Map) {
      throw const FormatException('Simulation response did not include created alert');
    }
    return AlertDto.fromJson(Map<String, dynamic>.from(created));
  }
}
