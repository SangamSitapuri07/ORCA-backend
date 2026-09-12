import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/config/app_config.dart';
import '../../../../core/live/live_channel.dart';
import '../../../../core/network/dio_provider.dart';
import '../../../../core/result/result.dart';
import '../../data/datasources/advisory_remote.dart';
import '../../data/repositories/advisory_repo_impl.dart';
import '../../domain/entities/advisory.dart';
import '../../domain/repositories/advisory_repo.dart';
import '../../domain/usecases/get_advisory.dart';

/// Provider for AdvisoryRemoteDataSource.
final advisoryRemoteDataSourceProvider = Provider<AdvisoryRemoteDataSource>((ref) {
  final dio = ref.watch(dioProvider);
  return AdvisoryRemoteDataSource(dio);
});

/// Provider for AdvisoryRepository.
final advisoryRepositoryProvider = Provider<AdvisoryRepository>((ref) {
  final remote = ref.watch(advisoryRemoteDataSourceProvider);
  final cache = ref.watch(cacheServiceProvider);
  return AdvisoryRepositoryImpl(
    remoteDataSource: remote,
    cacheService: cache,
  );
});

/// Provider for GetAdvisoryUseCase.
final getAdvisoryUseCaseProvider = Provider<GetAdvisoryUseCase>((ref) {
  final repo = ref.watch(advisoryRepositoryProvider);
  return GetAdvisoryUseCase(repo);
});

/// Current advisory location coordinates.
final advisoryLocationProvider = StateProvider<Map<String, double>>((ref) {
  return {'lat': AppConfig.defaultLat, 'lon': AppConfig.defaultLon};
});

/// StateNotifier providing live / cached advisory state.
class AdvisoryNotifier extends StateNotifier<AsyncValue<AdvisoryEntity>> {
  final Ref _ref;
  final GetAdvisoryUseCase _useCase;

  AdvisoryNotifier(this._ref, this._useCase) : super(const AsyncValue.loading()) {
    fetch();

    // Proactively refresh when SSE pushes data.updated event (§4, §16)
    _ref.listen(dataUpdatedStreamProvider, (prev, next) {
      next.whenData((_) {
        fetch(forceRefresh: true);
      });
    });
  }

  Future<void> fetch({bool forceRefresh = false}) async {
    state = const AsyncValue.loading();
    final coords = _ref.read(advisoryLocationProvider);

    final result = await _useCase.execute(
      lat: coords['lat'] ?? AppConfig.defaultLat,
      lon: coords['lon'] ?? AppConfig.defaultLon,
      forceRefresh: forceRefresh,
    );

    result.when(
      ok: (advisory) {
        state = AsyncValue.data(advisory);
      },
      err: (failure) {
        state = AsyncValue.error(failure.message, StackTrace.current);
      },
    );
  }
}

/// Provider managing Advisory state.
final advisoryProvider = StateNotifierProvider<AdvisoryNotifier, AsyncValue<AdvisoryEntity>>((ref) {
  final useCase = ref.watch(getAdvisoryUseCaseProvider);
  return AdvisoryNotifier(ref, useCase);
});
