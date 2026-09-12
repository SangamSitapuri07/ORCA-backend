import 'package:dio/dio.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/cache/staleness.dart';
import '../../../../core/result/app_failure.dart';
import '../../../../core/result/result.dart';

import '../../domain/entities/zone_snapshot.dart';
import '../../domain/repositories/map_repo.dart';
import '../datasources/map_remote.dart';
import '../dto/zone_dto.dart';

/// Implementation of MapRepository (§10).
class MapRepositoryImpl implements MapRepository {
  final MapRemoteDataSource _remoteDataSource;
  final CacheService _cacheService;

  MapRepositoryImpl({
    required MapRemoteDataSource remoteDataSource,
    required CacheService cacheService,
  })  : _remoteDataSource = remoteDataSource,
        _cacheService = cacheService;

  @override
  Future<Result<ZoneSnapshot>> probeZone({
    required double lat,
    required double lon,
  }) async {
    final cacheKey = 'zone_${lat.toStringAsFixed(2)}_${lon.toStringAsFixed(2)}';
    final cached = _cacheService.get(cacheKey);

    try {
      final dto = await _remoteDataSource.getZoneSnapshot(lat: lat, lon: lon);

      final jsonMap = <String, dynamic>{
        'lat': dto.lat,
        'lon': dto.lon,
        'zone_name': dto.zoneName,
        'offshore_dist_km': dto.offshoreDistKm,
        'depth_m': dto.depthM,
        'wave_height_m': dto.waveHeightM,
        'swell_period_s': dto.swellPeriodS,
        'wind_speed_kn': dto.windSpeedKn,
        'wind_direction': dto.windDirection,
        'sea_temp_c': dto.seaTempC,
        'current_speed_kn': dto.currentSpeedKn,
        'current_direction': dto.currentDirection,
        'chlorophyll_mg_m3': dto.chlorophyllMgM3,
        'fishing_effort_hours': dto.fishingEffortHours,
        'nearest_harbour': dto.nearestHarbour,
        'nearest_harbour_dist_km': dto.nearestHarbourDistKm,
        'sources': dto.sources,
        'sources_failed': dto.sourcesFailed,
        'timestamp': dto.timestampStr,
      };
      await _cacheService.put(cacheKey, jsonMap);

      final staleness = StalenessInfo.fromDateTime(DateTime.now());
      return Result.ok(dto.toEntity(staleness));
    } on DioException catch (dioErr) {
      if (cached != null) {
        final dto = ZoneDto.fromJson(cached.data);
        return Result.ok(dto.toEntity(cached.staleness));
      }
      if (dioErr.type == DioExceptionType.connectionTimeout) {
        return const Result.err(AppFailure.timeout());
      }
      return const Result.err(AppFailure.serverDown());
    } catch (e) {
      if (cached != null) {
        final dto = ZoneDto.fromJson(cached.data);
        return Result.ok(dto.toEntity(cached.staleness));
      }
      return Result.err(AppFailure.unknown(e.toString()));
    }
  }

  @override
  Future<Result<GeoLayerCollection>> getGeoLayers() async {
    try {
      final dto = await _remoteDataSource.getGeoLayers();
      return Result.ok(dto.toEntity());
    } on DioException catch (error) {
      if (error.type == DioExceptionType.connectionTimeout ||
          error.type == DioExceptionType.receiveTimeout) {
        return const Result.err(AppFailure.timeout());
      }
      return const Result.err(AppFailure.serverDown());
    } catch (error) {
      return Result.err(AppFailure.unknown(error.toString()));
    }
  }
}
