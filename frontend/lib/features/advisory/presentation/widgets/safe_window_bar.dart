import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../domain/entities/advisory.dart';

/// Renders safe departure window banner (§8).
class SafeWindowBar extends StatelessWidget {
  final SafeWindow? safeWindow;

  const SafeWindowBar({
    super.key,
    required this.safeWindow,
  });

  @override
  Widget build(BuildContext context) {
    if (safeWindow == null) {
      return const SizedBox.shrink();
    }

    final isSafe = safeWindow!.isSafe;
    final color = isSafe ? VerdictColors.go : VerdictColors.noGo;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: OrcaTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.5), width: 1.2),
      ),
      child: Row(
        children: [
          Icon(
            isSafe ? Icons.access_time_filled : Icons.timer_off_outlined,
            color: color,
            size: 24,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'SAFE DEPARTURE WINDOW',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: OrcaTheme.textSecondary,
                    letterSpacing: 0.8,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  isSafe
                      ? '${safeWindow!.from} to ${safeWindow!.to}'
                      : 'No safe departure window in next 48h',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    color: isSafe ? Colors.white : VerdictColors.noGo,
                  ),
                ),
              ],
            ),
          ),
          if (safeWindow!.hoursRemaining != null && isSafe) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: VerdictColors.go.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '${safeWindow!.hoursRemaining!.toStringAsFixed(1)}h left',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: VerdictColors.go,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
