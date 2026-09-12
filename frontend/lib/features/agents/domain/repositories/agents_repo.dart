import '../../../../core/result/result.dart';
import '../entities/agent_reasoning.dart';

/// Contract for agent reasoning and collaboration trace access (§10).
abstract class AgentsRepository {
  /// Fetches multi-agent reasoning trace.
  Future<Result<AgentReasoningResult>> getReasoning({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  });
}
