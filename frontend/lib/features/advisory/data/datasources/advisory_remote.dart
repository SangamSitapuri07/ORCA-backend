import 'package:dio/dio.dart';
import '../../../../core/config/api_paths.dart';
import '../dto/advisory_dto.dart';

/// Remote datasource communicating with /api/v1/advisory (§4).
class AdvisoryRemoteDataSource {
  final Dio _dio;

  AdvisoryRemoteDataSource(this._dio);

  /// Fetches advisory snapshot for given lat/lon.
  Future<AdvisoryDto> getAdvisory({
    required double lat,
    required double lon,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      ApiPaths.advisory,
      queryParameters: <String, dynamic>{
        'lat': lat,
        'lon': lon,
      },
    );

    if (response.data == null) {
      throw Exception('Empty response received for advisory');
    }

    return AdvisoryDto.fromJson(response.data!);
  }
}
