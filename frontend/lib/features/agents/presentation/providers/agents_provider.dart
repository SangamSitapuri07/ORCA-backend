import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/network/dio_provider.dart';
import '../../../../core/result/result.dart';
import '../../../advisory/presentation/providers/advisory_provider.dart';
import '../../data/datasources/agents_remote.dart';
import '../../data/repositories/agents_repo_impl.dart';
import '../../domain/entities/agent_reasoning.dart';
import '../../domain/repositories/agents_repo.dart';
import '../../domain/usecases/get_agent_reasoning.dart';

/// Provider for AgentsRemoteDataSource.
final agentsRemoteDataSourceProvider = Provider<AgentsRemoteDataSource>((ref) {
  final dio = ref.watch(dioProvider);
  return AgentsRemoteDataSource(dio);
});

/// Provider for AgentsRepository.
final agentsRepositoryProvider = Provider<AgentsRepository>((ref) {
  final remote = ref.watch(agentsRemoteDataSourceProvider);
  final cache = ref.watch(cacheServiceProvider);
  return AgentsRepositoryImpl(
    remoteDataSource: remote,
    cacheService: cache,
  );
});

/// Provider for GetAgentReasoningUseCase.
final getAgentReasoningUseCaseProvider = Provider<GetAgentReasoningUseCase>((ref) {
  final repo = ref.watch(agentsRepositoryProvider);
  return GetAgentReasoningUseCase(repo);
});

/// StateNotifier providing live / cached multi-agent reasoning state.
class AgentsNotifier extends StateNotifier<AsyncValue<AgentReasoningResult>> {
  final Ref _ref;
  final GetAgentReasoningUseCase _useCase;

  AgentsNotifier(this._ref, this._useCase) : super(const AsyncValue.loading()) {
    fetch();
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
      ok: (reasoning) {
        state = AsyncValue.data(reasoning);
      },
      err: (failure) {
        state = AsyncValue.error(failure.message, StackTrace.current);
      },
    );
  }
}

/// Provider managing multi-agent reasoning state.
final agentsProvider = StateNotifierProvider<AgentsNotifier, AsyncValue<AgentReasoningResult>>((ref) {
  final useCase = ref.watch(getAgentReasoningUseCaseProvider);
  return AgentsNotifier(ref, useCase);
});
