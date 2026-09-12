import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:orca_app/core/cache/cache_service.dart';
import 'package:orca_app/features/advisory/data/datasources/advisory_remote.dart';
import 'package:orca_app/features/advisory/data/dto/advisory_dto.dart';
import 'package:orca_app/features/advisory/data/repositories/advisory_repo_impl.dart';

class MockAdvisoryRemoteDataSource extends Mock implements AdvisoryRemoteDataSource {}
class MockCacheService extends Mock implements CacheService {}

void main() {
  late MockAdvisoryRemoteDataSource mockRemote;
  late MockCacheService mockCache;
  late AdvisoryRepositoryImpl repository;

  setUp(() {
    mockRemote = MockAdvisoryRemoteDataSource();
    mockCache = MockCacheService();
    repository = AdvisoryRepositoryImpl(
      remoteDataSource: mockRemote,
      cacheService: mockCache,
    );
  });

  group('AdvisoryRepository Tests', () {
    test('Returns Ok<AdvisoryEntity> on remote success and writes to cache', () async {
      when(() => mockCache.get(any())).thenReturn(null);
      when(() => mockCache.put(any(), any())).thenAnswer((_) async {});

      final fakeDto = AdvisoryDto(
        verdict: 'go',
        headline: 'Safe sea conditions today.',
        plainEn: ['Clear weather'],
        plainHi: [],
        sources: ['Open-Meteo'],
        sourcesFailed: [],
        knownSources: 4,
        totalSources: 4,
      );

      when(() => mockRemote.getAdvisory(lat: any(named: 'lat'), lon: any(named: 'lon')))
          .thenAnswer((_) async => fakeDto);

      final result = await repository.getAdvisory(lat: 18.92, lon: 72.83);

      expect(result.isOk, isTrue);
      expect(result.valueOrNull?.verdict, equals('go'));
      verify(() => mockCache.put(any(), any())).called(1);
    });

    test('Falls back to cached advisory with staleness when remote throws network error', () async {
      final cachedRecord = CachedRecord(
        data: {
          'verdict': 'caution',
          'headline': 'Cached previous advisory',
          'plain_en': [],
          'plain_hi': [],
          'sources': [],
          'data_coverage': {'known': 3, 'total': 4, 'sources_failed': []},
        },
        fetchedAt: DateTime.now().subtract(const Duration(hours: 4)),
        ttl: const Duration(minutes: 30),
      );

      when(() => mockCache.get(any())).thenReturn(cachedRecord);
      when(() => mockRemote.getAdvisory(lat: any(named: 'lat'), lon: any(named: 'lon')))
          .thenThrow(DioException(requestOptions: RequestOptions(path: '/api/v1/advisory'), type: DioExceptionType.connectionError));

      final result = await repository.getAdvisory(lat: 18.92, lon: 72.83, forceRefresh: true);

      expect(result.isOk, isTrue);
      expect(result.valueOrNull?.verdict, equals('caution'));
      expect(result.valueOrNull?.staleness.label, contains('4h ago'));
    });
  });
}
