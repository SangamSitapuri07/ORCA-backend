import 'package:dio/dio.dart';
import '../../../../core/config/api_paths.dart';
import '../dto/alert_dto.dart';
import '../dto/alerts_snapshot_dto.dart';

/// Remote datasource for live and explicitly simulated ORCA Box alerts.
class AlertsRemoteDataSource {
  final Dio _dio;

  AlertsRemoteDataSource(this._dio);

  Future<AlertsSnapshotDto> getActiveAlerts({
    required double lat,
    required double lon,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      ApiPaths.alerts,
      queryParameters: <String, dynamic>{'lat': lat, 'lon': lon},
    );
    final data = response.data;
    if (data == null) {
      throw const FormatException('Alert response was empty');
    }
    return AlertsSnapshotDto.fromJson(data);
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
