import '../../../../core/agents/agent_registry.dart';
import '../../../../core/cache/staleness.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../domain/entities/agent_reasoning.dart';

/// DTO for /api/v1/reason. Supports the real ORCA Box trace fields.
class ReasonDto {
  final String overallRisk;
  final String verdict;
  final Map<String, dynamic>? dataCoverage;
  final List<dynamic> agentsList;
  final Map<String, dynamic>? synthesisJson;
  final List<String> failedSources;
  final String? fetchedAt;
  final String summary;
  final String recommendation;

  ReasonDto({
    required this.overallRisk,
    required this.verdict,
    this.dataCoverage,
    required this.agentsList,
    this.synthesisJson,
    required this.failedSources,
    this.fetchedAt,
    required this.summary,
    required this.recommendation,
  });

  static List<String> _strings(dynamic value) => value is List
      ? value.map((item) => item.toString()).toList()
      : <String>[];

  factory ReasonDto.fromJson(Map<String, dynamic> json) {
    final coverage = json['data_coverage'] is Map
        ? Map<String, dynamic>.from(json['data_coverage'] as Map)
        : null;
    final failed = _strings(json['data_sources_failed']).isNotEmpty
        ? _strings(json['data_sources_failed'])
        : _strings(coverage?['failed_sources'] ?? coverage?['sources_failed']);
    return ReasonDto(
      overallRisk: json['overall_risk'] as String? ?? 'unknown',
      verdict: json['verdict'] as String? ?? 'unknown',
      dataCoverage: coverage,
      agentsList: json['agents'] is List ? json['agents'] as List : const [],
      synthesisJson: json['orchestrator_synthesis'] is Map
          ? Map<String, dynamic>.from(json['orchestrator_synthesis'] as Map)
          : null,
      failedSources: failed,
      fetchedAt: json['fetched_at'] as String?,
      summary: json['summary'] as String? ?? 'Reasoning summary unavailable.',
      recommendation: json['recommendation'] as String? ?? 'Recommendation unavailable.',
    );
  }

  AgentReasoningResult toEntity(StalenessInfo staleness) {
    final known = dataCoverage?['known'] as int? ?? 0;
    final total = dataCoverage?['total'] as int? ?? 0;
    final parsedAgents = <AgentTraceFinding>[];

    for (final raw in agentsList) {
      if (raw is! Map) continue;
      final agent = Map<String, dynamic>.from(raw);
      final id = (agent['agent_id'] ?? agent['agent']) as String? ?? 'unknown';
      final descriptor = AgentRegistry.findById(id);
      final evidence = _strings(agent['evidence']);
      final warnings = _strings(agent['warnings']);
      if (agent['findings'] is List) {
        for (final findingRaw in agent['findings'] as List) {
          if (findingRaw is! Map) continue;
          final finding = Map<String, dynamic>.from(findingRaw);
          final message = finding['msg']?.toString();
          if (message == null || message.isEmpty) continue;
          evidence.add(message);
          if (<String>{'warn', 'high', 'critical'}.contains(finding['severity'])) {
            warnings.add(message);
          }
        }
      }
      parsedAgents.add(AgentTraceFinding(
        agentId: id,
        name: (agent['name'] ?? agent['agent_name']) as String? ?? descriptor.name,
        emoji: agent['emoji'] as String? ?? descriptor.emoji,
        agentClass: (agent['execution_class'] ?? agent['class'] ?? descriptor.classLabel).toString(),
        status: agent['status'] as String? ?? 'unknown',
        durationMs: (agent['duration_ms'] as num?)?.toInt() ?? 0,
        verdict: (agent['risk_level'] ?? agent['verdict']) as String? ?? 'unknown',
        summary: agent['summary'] as String? ?? 'No agent summary returned.',
        evidence: evidence,
        warnings: warnings,
        llmInvoked: agent['llm_invoked'] == true,
        llmInterpretation: agent['llm_interpretation'] as String?,
        ragInvoked: agent['rag_invoked'] == true,
      ));
    }

    final timestampValue = synthesisJson?['timestamp'] as String? ?? fetchedAt;
    final synthesis = OrchestratorSynthesis(
      headline: synthesisJson?['headline'] as String? ?? summary,
      recommendation: synthesisJson?['recommendation'] as String? ?? recommendation,
      traceOwner: synthesisJson?['trace_owner'] as String? ?? 'ORCA Box reasoner',
      timestamp: DateFormatter.parseIso(timestampValue) ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    );

    return AgentReasoningResult(
      overallRisk: overallRisk,
      verdict: verdict,
      knownSources: known,
      totalSources: total,
      sourcesFailed: failedSources,
      agents: parsedAgents,
      orchestratorSynthesis: synthesis,
      staleness: staleness,
    );
  }
}
