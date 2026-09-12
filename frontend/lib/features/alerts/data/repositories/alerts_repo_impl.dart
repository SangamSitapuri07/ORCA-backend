import 'package:dio/dio.dart';
import '../../../../core/network/dio_failure_mapper.dart';
import '../../../../core/result/app_failure.dart';
import '../../../../core/result/result.dart';
import '../../domain/entities/alert_item.dart';
import '../../domain/entities/alerts_snapshot.dart';
import '../../domain/repositories/alerts_repo.dart';
import '../datasources/alerts_remote.dart';

class AlertsRepositoryImpl implements AlertsRepository {
  final AlertsRemoteDataSource _remoteDataSource;

  AlertsRepositoryImpl({required AlertsRemoteDataSource remoteDataSource})
      : _remoteDataSource = remoteDataSource;

  @override
  Future<Result<AlertsSnapshot>> getActiveAlerts({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  }) async {
    try {
      final dto = await _remoteDataSource.getActiveAlerts(lat: lat, lon: lon);
      return Result.ok(dto.toEntity());
    } on DioException catch (error) {
      return Result.err(mapDioFailure(error));
    } catch (error) {
      return Result.err(AppFailure.unknown(error.toString()));
    }
  }

  @override
  Future<Result<AlertItem>> simulateAlert({
    required double lat,
    required double lon,
  }) async {
    try {
      final dto = await _remoteDataSource.simulateAlert(lat: lat, lon: lon);
      return Result.ok(dto.toEntity());
    } on DioException catch (error) {
      return Result.err(mapDioFailure(error));
    } catch (error) {
      return Result.err(AppFailure.unknown(error.toString()));
    }
  }
}
