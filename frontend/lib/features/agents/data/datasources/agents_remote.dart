import 'package:dio/dio.dart';
import '../../../../core/config/api_paths.dart';
import '../dto/reason_dto.dart';

/// Remote datasource for Agents Reasoning endpoint (/api/v1/reason).
class AgentsRemoteDataSource {
  final Dio _dio;

  AgentsRemoteDataSource(this._dio);

  /// Runs multi-agent reasoning over live observation at [lat], [lon].
  Future<ReasonDto> runReasoning({
    required double lat,
    required double lon,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      ApiPaths.reason,
      queryParameters: <String, dynamic>{
        'lat': lat,
        'lon': lon,
      },
    );

    if (response.data == null) {
      throw Exception('Empty response received from reasoner endpoint');
    }

    return ReasonDto.fromJson(response.data!);
  }
}
