import 'package:dio/dio.dart';
import '../../../../core/config/api_paths.dart';
import '../dto/geo_layers_dto.dart';
import '../dto/zone_dto.dart';

/// Remote datasource for Map endpoints (/api/v1/zone, /api/v1/layers).
class MapRemoteDataSource {
  final Dio _dio;

  MapRemoteDataSource(this._dio);

  /// Probes single spot snapshot at given lat/lon.
  Future<ZoneDto> getZoneSnapshot({
    required double lat,
    required double lon,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      ApiPaths.zone,
      queryParameters: <String, dynamic>{
        'lat': lat,
        'lon': lon,
      },
    );

    if (response.data == null) {
      throw Exception('Empty response received for zone probe');
    }

    return ZoneDto.fromJson(response.data!);
  }

  /// Fetches real PFZ, cyclone, harbour and EEZ GeoJSON from the ORCA Box.
  Future<GeoLayersDto> getGeoLayers() async {
    final response = await _dio.get<Map<String, dynamic>>(ApiPaths.layers);
    if (response.data == null) {
      throw const FormatException('Empty GeoJSON layer response');
    }
    return GeoLayersDto(response.data!);
  }
}
