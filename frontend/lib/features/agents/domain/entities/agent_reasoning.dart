import '../../../../core/cache/staleness.dart';

/// Single agent execution record in the collaboration trace (§3, §10, §27).
class AgentTraceFinding {
  final String agentId;
  final String name;
  final String emoji;
  final String agentClass; // DETERMINISTIC or LLM
  final String status; // completed, running, degraded, failed
  final int durationMs;
  final String verdict; // good, caution, danger
  final String summary;
  final List<String> evidence;
  final List<String> warnings;
  final bool llmInvoked;
  final String? llmInterpretation;
  final bool ragInvoked;

  const AgentTraceFinding({
    required this.agentId,
    required this.name,
    required this.emoji,
    required this.agentClass,
    required this.status,
    required this.durationMs,
    required this.verdict,
    required this.summary,
    required this.evidence,
    required this.warnings,
    this.llmInvoked = false,
    this.llmInterpretation,
    this.ragInvoked = false,
  });
}

/// Orchestrator synthesis record (§3).
class OrchestratorSynthesis {
  final String headline;
  final String recommendation;
  final String traceOwner;
  final DateTime timestamp;

  const OrchestratorSynthesis({
    required this.headline,
    required this.recommendation,
    required this.traceOwner,
    required this.timestamp,
  });
}

/// Complete multi-agent reasoning result entity.
class AgentReasoningResult {
  final String overallRisk;
  final String verdict;
  final int knownStages;
  final int totalStages;
  final List<String> sourcesFailed;
  final List<AgentTraceFinding> agents;
  final OrchestratorSynthesis orchestratorSynthesis;
  final StalenessInfo staleness;

  const AgentReasoningResult({
    required this.overallRisk,
    required this.verdict,
    required this.knownStages,
    required this.totalStages,
    required this.sourcesFailed,
    required this.agents,
    required this.orchestratorSynthesis,
    required this.staleness,
  });
}
