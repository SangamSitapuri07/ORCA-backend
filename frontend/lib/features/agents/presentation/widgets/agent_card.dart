import 'package:flutter/material.dart';
import '../../../../core/agents/agent_registry.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../domain/entities/agent_reasoning.dart';

/// Card displaying findings, evidence chips, and verdict for a single agent (§3, §27).
class AgentCard extends StatelessWidget {
  final AgentTraceFinding finding;

  const AgentCard({
    super.key,
    required this.finding,
  });

  @override
  Widget build(BuildContext context) {
    final descriptor = AgentRegistry.findById(finding.agentId);
    final verdictColor = VerdictColors.fromVerdict(finding.verdict);

    return Container(
      padding: const EdgeInsets.all(14),
      margin: const EdgeInsets.symmetric(vertical: 5),
      decoration: BoxDecoration(
        color: OrcaTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: finding.verdict != 'good'
              ? verdictColor.withValues(alpha: 0.6)
              : OrcaTheme.cardBorder,
          width: finding.verdict != 'good' ? 1.4 : 1.0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Agent Header: Emoji + Name + Class Tag + Verdict Pill
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Text(
                    finding.emoji,
                    style: const TextStyle(fontSize: 22),
                  ),
                  const SizedBox(width: 10),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        finding.name,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                            decoration: BoxDecoration(
                              color: descriptor.accentColor.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              finding.agentClass,
                              style: TextStyle(
                                fontSize: 9,
                                fontWeight: FontWeight.bold,
                                color: descriptor.accentColor,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            '${finding.durationMs}ms',
                            style: const TextStyle(
                              fontSize: 10,
                              color: OrcaTheme.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
              // Verdict Icon
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: verdictColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      VerdictColors.iconForVerdict(finding.verdict),
                      color: verdictColor,
                      size: 14,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      finding.verdict.toUpperCase(),
                      style: TextStyle(
                        color: verdictColor,
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),

          // Finding Summary
          Text(
            finding.summary,
            style: const TextStyle(
              fontSize: 12.5,
              color: OrcaTheme.textPrimary,
              height: 1.35,
            ),
          ),

          if (finding.llmInterpretation != null) ...[
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFF1E1B4B),
                borderRadius: BorderRadius.circular(7),
              ),
              child: Text(
                'LOCAL OLLAMA EXPLANATION\n${finding.llmInterpretation}',
                style: const TextStyle(fontSize: 11, color: Color(0xFFC7D2FE), height: 1.35),
              ),
            ),
          ],

          // Evidence chips if present
          if (finding.evidence.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: finding.evidence.map(
                (ev) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: OrcaTheme.surfaceElevated,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: OrcaTheme.cardBorder, width: 0.8),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.check, size: 10, color: OrcaTheme.accent),
                      const SizedBox(width: 4),
                      Text(
                        ev,
                        style: const TextStyle(
                          fontSize: 10.5,
                          color: OrcaTheme.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ).toList(),
            ),
          ],

          // Warnings if present
          if (finding.warnings.isNotEmpty) ...[
            const SizedBox(height: 6),
            ...finding.warnings.map(
              (w) => Row(
                children: [
                  const Icon(Icons.warning_amber_rounded, size: 12, color: VerdictColors.caution),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      w,
                      style: const TextStyle(
                        fontSize: 11,
                        color: VerdictColors.caution,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
