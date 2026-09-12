import '../../../../core/result/result.dart';
import '../entities/agent_reasoning.dart';
import '../repositories/agents_repo.dart';

/// Usecase for running eleven-stage reasoning pipeline (§10).
class GetAgentReasoningUseCase {
  final AgentsRepository _repository;

  GetAgentReasoningUseCase(this._repository);

  Future<Result<AgentReasoningResult>> execute({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  }) {
    return _repository.getReasoning(
      lat: lat,
      lon: lon,
      forceRefresh: forceRefresh,
    );
  }
}
