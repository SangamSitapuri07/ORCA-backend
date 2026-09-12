import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/risk_pill.dart';
import '../../../../core/widgets/staleness_badge.dart';
import '../../domain/entities/agent_reasoning.dart';
import 'agent_card.dart';

/// Backend trace displaying the actual eleven-stage orchestration sequence (§3, §27).
class CollaborationTraceView extends StatelessWidget {
  final AgentReasoningResult reasoning;

  const CollaborationTraceView({
    super.key,
    required this.reasoning,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Top Overview Banner: Overall Risk + Data Coverage + Staleness
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: OrcaTheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: OrcaTheme.cardBorder),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      const Text(
                        'ANALYTICAL CONTEXT RISK:',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: OrcaTheme.textSecondary,
                        ),
                      ),
                      const SizedBox(width: 8),
                      RiskPill(risk: reasoning.overallRisk),
                    ],
                  ),
                  StalenessBadge(staleness: reasoning.staleness),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.shield_outlined, size: 14, color: OrcaTheme.accent),
                  const SizedBox(width: 6),
                  Text(
                    'Known stage status: ${reasoning.knownStages}/${reasoning.totalStages}',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: OrcaTheme.textPrimary,
                    ),
                  ),
                ],
              ),
              if (reasoning.sourcesFailed.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  'Degraded/Failed: ${reasoning.sourcesFailed.join(", ")}',
                  style: const TextStyle(
                    fontSize: 11,
                    color: VerdictColors.caution,
                  ),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 14),

        // Orchestrator Synthesis Card (§3, §27)
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFF1E1B4B), // Deep indigo
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFF6366F1), width: 1.2),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Row(
                    children: [
                      Text('🧠', style: TextStyle(fontSize: 18)),
                      SizedBox(width: 6),
                      Text(
                        'ORCHESTRATOR SYNTHESIS',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFFA5B4FC),
                          letterSpacing: 0.8,
                        ),
                      ),
                    ],
                  ),
                  Text(
                    reasoning.orchestratorSynthesis.traceOwner,
                    style: const TextStyle(
                      fontSize: 10,
                      color: Color(0xFFC7D2FE),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                reasoning.orchestratorSynthesis.headline,
                style: const TextStyle(
                  fontSize: 13.5,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                reasoning.orchestratorSynthesis.recommendation,
                style: const TextStyle(
                  fontSize: 12,
                  color: Color(0xFFE0E7FF),
                  height: 1.3,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),

        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 4, vertical: 4),
          child: Text(
            'PER-AGENT FINDINGS & QC GATES',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              color: OrcaTheme.textSecondary,
              letterSpacing: 0.8,
            ),
          ),
        ),
        const SizedBox(height: 6),

        // Stage cards rendered dynamically from backend execution
        ...reasoning.agents.map((agent) => AgentCard(finding: agent)),
      ],
    );
  }
}
