import 'package:dio/dio.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/cache/staleness.dart';
import '../../../../core/result/app_failure.dart';
import '../../../../core/result/result.dart';
import '../../domain/entities/advisory.dart';
import '../../domain/repositories/advisory_repo.dart';
import '../datasources/advisory_remote.dart';
import '../dto/advisory_dto.dart';

/// Implementation of AdvisoryRepository with cache-first and staleness guarantees (§10, §13).
class AdvisoryRepositoryImpl implements AdvisoryRepository {
  final AdvisoryRemoteDataSource _remoteDataSource;
  final CacheService _cacheService;

  AdvisoryRepositoryImpl({
    required AdvisoryRemoteDataSource remoteDataSource,
    required CacheService cacheService,
  })  : _remoteDataSource = remoteDataSource,
        _cacheService = cacheService;

  @override
  Future<Result<AdvisoryEntity>> getAdvisory({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  }) async {
    final cacheKey = 'advisory_${lat.toStringAsFixed(2)}_${lon.toStringAsFixed(2)}';
    final cached = _cacheService.get(cacheKey);

    // 1. If not forcing refresh and cache is fresh, emit cached
    if (!forceRefresh && cached != null && !cached.isExpired) {
      final dto = AdvisoryDto.fromJson(cached.data);
      return Result.ok(dto.toEntity(cached.staleness));
    }

    // 2. Fetch live data
    try {
      final dto = await _remoteDataSource.getAdvisory(lat: lat, lon: lon);

      // Write-through to cache
      final jsonMap = <String, dynamic>{
        'verdict': dto.verdict,
        'color': dto.color,
        'headline': dto.headline,
        'headline_hi': dto.headlineHi,
        'plain_en': dto.plainEn,
        'plain_hi': dto.plainHi,
        'safe_window': dto.safeWindowJson,
        'variables': dto.variablesJson,
        'hourly_chart': dto.hourlyChartJson,
        'sources': dto.sources,
        'data_coverage': {
          'known': dto.knownSources,
          'total': dto.totalSources,
          'sources_failed': dto.sourcesFailed,
        },
        'timestamp': dto.timestampStr,
      };
      await _cacheService.put(cacheKey, jsonMap);

      final freshStaleness = StalenessInfo.fromDateTime(DateTime.now());
      return Result.ok(dto.toEntity(freshStaleness));
    } on DioException catch (dioErr) {
      // 3. Network error -> Fall back to cache if present with honest staleness
      if (cached != null) {
        final dto = AdvisoryDto.fromJson(cached.data);
        return Result.ok(dto.toEntity(cached.staleness));
      }

      if (dioErr.type == DioExceptionType.connectionTimeout ||
          dioErr.type == DioExceptionType.receiveTimeout) {
        return const Result.err(AppFailure.timeout());
      }
      if (dioErr.type == DioExceptionType.connectionError) {
        return const Result.err(AppFailure.serverDown());
      }
      return Result.err(AppFailure.unknown(dioErr.message ?? 'Network error'));
    } catch (e) {
      if (cached != null) {
        final dto = AdvisoryDto.fromJson(cached.data);
        return Result.ok(dto.toEntity(cached.staleness));
      }
      return Result.err(AppFailure.unknown(e.toString()));
    }
  }
}
