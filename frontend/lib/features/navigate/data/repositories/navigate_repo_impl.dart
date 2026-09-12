import 'package:dio/dio.dart';
import '../../../../core/result/app_failure.dart';
import '../../../../core/result/result.dart';
import '../../domain/entities/route_advisory.dart';
import '../../domain/entities/route_check.dart';
import '../../domain/repositories/navigate_repo.dart';
import '../datasources/navigate_remote.dart';

/// Implementation of NavigateRepository (§10).
class NavigateRepositoryImpl implements NavigateRepository {
  final NavigateRemoteDataSource _remoteDataSource;

  NavigateRepositoryImpl({required NavigateRemoteDataSource remoteDataSource})
      : _remoteDataSource = remoteDataSource;

  @override
  Future<Result<RouteCheckEntity>> checkRoute({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  }) async {
    try {
      final dto = await _remoteDataSource.checkRoute(
        fromLat: fromLat,
        fromLon: fromLon,
        toLat: toLat,
        toLon: toLon,
      );
      return Result.ok(dto.toEntity());
    } on DioException catch (dioErr) {
      if (dioErr.type == DioExceptionType.connectionTimeout) {
        return const Result.err(AppFailure.timeout());
      }
      return const Result.err(AppFailure.serverDown());
    } catch (e) {
      return Result.err(AppFailure.unknown(e.toString()));
    }
  }

  @override
  Future<Result<RouteAdvisoryEntity>> getRouteAdvisory({
    required double fromLat,
    required double fromLon,
    required double toLat,
    required double toLon,
  }) async {
    try {
      final dto = await _remoteDataSource.getRouteAdvisory(
        fromLat: fromLat,
        fromLon: fromLon,
        toLat: toLat,
        toLon: toLon,
      );
      return Result.ok(dto.toEntity());
    } on DioException catch (dioErr) {
      if (dioErr.type == DioExceptionType.connectionTimeout) {
        return const Result.err(AppFailure.timeout());
      }
      return const Result.err(AppFailure.serverDown());
    } catch (e) {
      return Result.err(AppFailure.unknown(e.toString()));
    }
  }
}
