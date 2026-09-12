import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/live/live_channel.dart';
import '../../../../core/network/dio_provider.dart';
import '../../../../core/result/result.dart';
import '../../../advisory/presentation/providers/advisory_provider.dart';
import '../../data/datasources/alerts_remote.dart';
import '../../data/dto/alert_dto.dart';
import '../../data/repositories/alerts_repo_impl.dart';
import '../../domain/entities/alert_item.dart';
import '../../domain/entities/alerts_snapshot.dart';
import '../../domain/repositories/alerts_repo.dart';
import '../../domain/usecases/get_alerts.dart';

/// Provider for AlertsRemoteDataSource.
final alertsRemoteDataSourceProvider = Provider<AlertsRemoteDataSource>((ref) {
  final dio = ref.watch(dioProvider);
  return AlertsRemoteDataSource(dio);
});

/// Provider for AlertsRepository.
final alertsRepositoryProvider = Provider<AlertsRepository>((ref) {
  final remote = ref.watch(alertsRemoteDataSourceProvider);
  return AlertsRepositoryImpl(remoteDataSource: remote);
});

/// Provider for GetAlertsUseCase.
final getAlertsUseCaseProvider = Provider<GetAlertsUseCase>((ref) {
  final repo = ref.watch(alertsRepositoryProvider);
  return GetAlertsUseCase(repo);
});

/// StateNotifier managing active marine alerts with SSE subscription.
class AlertsNotifier extends StateNotifier<AsyncValue<AlertsSnapshot>> {
  final Ref _ref;
  final GetAlertsUseCase _useCase;

  AlertsNotifier(this._ref, this._useCase) : super(const AsyncValue.loading()) {
    fetch();

    // Listen to live SSE alert.push events (§4, §16)
    _ref.listen(alertPushStreamProvider, (prev, next) {
      next.whenData((event) {
        final data = event.jsonData;
        if (data is Map<String, dynamic>) {
          final dto = AlertDto.fromJson(data);
          final incoming = dto.toEntity();
          final current = state.valueOrNull ?? const AlertsSnapshot(alerts: <AlertItem>[]);
          state = AsyncValue.data(current.withAlerts(<AlertItem>[
            incoming,
            ...current.alerts.where((alert) => alert.id != incoming.id),
          ]));
        }
      });
    });
  }

  Future<void> fetch({bool forceRefresh = false}) async {
    state = const AsyncValue.loading();
    final coordinates = _ref.read(selectedCoordinatesProvider);
    final result = await _useCase.execute(
      lat: coordinates['lat']!,
      lon: coordinates['lon']!,
      forceRefresh: forceRefresh,
    );
    result.when(
      ok: (alerts) {
        state = AsyncValue.data(alerts);
      },
      err: (failure) {
        state = AsyncValue.error(failure.message, StackTrace.current);
      },
    );
  }

  /// Requests the backend's clearly labelled disaster-drill alert.
  Future<bool> simulateDemoAlert() async {
    final coordinates = _ref.read(selectedCoordinatesProvider);
    final result = await _useCase.simulate(
      lat: coordinates['lat']!,
      lon: coordinates['lon']!,
    );
    if (result.isOk) {
      final simulated = result.valueOrNull!;
      final current = state.valueOrNull ?? const AlertsSnapshot(alerts: <AlertItem>[]);
      state = AsyncValue.data(current.withAlerts(<AlertItem>[
        simulated,
        ...current.alerts.where((alert) => alert.id != simulated.id),
      ]));
      return true;
    }
    state = AsyncValue.error(
      result.failureOrNull?.message ?? 'Drill alert request failed.',
      StackTrace.current,
    );
    return false;
  }
}

/// Provider managing active marine alerts list.
final alertsProvider = StateNotifierProvider<AlertsNotifier, AsyncValue<AlertsSnapshot>>((ref) {
  final useCase = ref.watch(getAlertsUseCaseProvider);
  return AlertsNotifier(ref, useCase);
});
