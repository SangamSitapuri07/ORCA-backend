import 'package:flutter/material.dart';
import '../theme/verdict_colors.dart';

/// Compact chip displaying risk level (LOW / MODERATE / HIGH / CRITICAL).
class RiskPill extends StatelessWidget {
  final String risk;

  const RiskPill({
    super.key,
    required this.risk,
  });

  @override
  Widget build(BuildContext context) {
    final color = VerdictColors.fromVerdict(risk);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color, width: 1.0),
      ),
      child: Text(
        risk.toUpperCase(),
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w800,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}
