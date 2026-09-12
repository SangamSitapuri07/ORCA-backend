import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/network/dio_provider.dart';
import '../../data/datasources/map_remote.dart';
import '../../data/repositories/map_repo_impl.dart';
import '../../domain/entities/zone_snapshot.dart';
import '../../domain/repositories/map_repo.dart';
import '../../domain/usecases/get_zone_snapshot.dart';

/// Provider for MapRemoteDataSource.
final mapRemoteDataSourceProvider = Provider<MapRemoteDataSource>((ref) {
  final dio = ref.watch(dioProvider);
  return MapRemoteDataSource(dio);
});

/// Provider for MapRepository.
final mapRepositoryProvider = Provider<MapRepository>((ref) {
  final remote = ref.watch(mapRemoteDataSourceProvider);
  final cache = ref.watch(cacheServiceProvider);
  return MapRepositoryImpl(
    remoteDataSource: remote,
    cacheService: cache,
  );
});

/// Provider for GetZoneSnapshotUseCase.
final getZoneSnapshotUseCaseProvider = Provider<GetZoneSnapshotUseCase>((ref) {
  final repo = ref.watch(mapRepositoryProvider);
  return GetZoneSnapshotUseCase(repo);
});

/// User-selected visibility for the real backend GeoJSON layers.
final mapLayersProvider = StateProvider<List<MapLayerEntity>>((ref) {
  return const <MapLayerEntity>[
    MapLayerEntity(id: 'official_pfz', name: 'Official PFZ Lines', unit: 'WFS', source: 'INCOIS', tileUrl: '', isEnabled: true),
    MapLayerEntity(id: 'cyclone', name: 'Active Cyclones', unit: 'JTWC', source: 'JTWC', tileUrl: '', isEnabled: true),
    MapLayerEntity(id: 'port', name: 'Fishing Harbours', unit: 'points', source: 'ORCA static gazetteer; citations pending', tileUrl: '', isEnabled: true),
    MapLayerEntity(id: 'eez', name: 'India EEZ Boundary', unit: 'boundary', source: 'MarineRegions', tileUrl: '', isEnabled: false),
  ];
});

/// Real GIS overlays loaded through use-case → repository → remote datasource.
final geoLayersProvider = FutureProvider<GeoLayerCollection>((ref) async {
  final useCase = ref.watch(getZoneSnapshotUseCaseProvider);
  final result = await useCase.getGeoLayers();
  return result.when(
    ok: (layers) => layers,
    err: (failure) => throw StateError(failure.message),
  );
});

/// Probed zone snapshot state provider.
final probedZoneProvider = StateProvider<AsyncValue<ZoneSnapshot?>?>((ref) => null);

/// Helper function to probe coordinate.
Future<void> probeCoordinate(WidgetRef ref, double lat, double lon) async {
  ref.read(probedZoneProvider.notifier).state = const AsyncValue.loading();
  final useCase = ref.read(getZoneSnapshotUseCaseProvider);
  final result = await useCase.execute(lat: lat, lon: lon);

  result.when(
    ok: (snapshot) {
      ref.read(probedZoneProvider.notifier).state = AsyncValue.data(snapshot);
    },
    err: (failure) {
      ref.read(probedZoneProvider.notifier).state = AsyncValue.error(failure.message, StackTrace.current);
    },
  );
}
