import 'package:flutter/material.dart';
import '../theme/orca_theme.dart';
import '../theme/verdict_colors.dart';

/// Clean, high-contrast metric tile with unit, source provenance, and threshold coloring.
class StatTile extends StatelessWidget {
  final String label;
  final String value;
  final String? unit;
  final IconData icon;
  final String? source;
  final String? time;
  final String? status; // good, caution, danger
  final VoidCallback? onTap;

  const StatTile({
    super.key,
    required this.label,
    required this.value,
    this.unit,
    required this.icon,
    this.source,
    this.time,
    this.status,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final statusColor = status != null ? VerdictColors.fromVerdict(status) : OrcaTheme.textPrimary;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: OrcaTheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: status != null && status != 'good'
                ? statusColor.withValues(alpha: 0.6)
                : OrcaTheme.cardBorder,
            width: status != null && status != 'good' ? 1.5 : 1.0,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: OrcaTheme.textSecondary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Icon(icon, size: 18, color: statusColor),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(
                  value,
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    color: statusColor,
                    letterSpacing: 0.5,
                  ),
                ),
                if (unit != null) ...[
                  const SizedBox(width: 4),
                  Text(
                    unit!,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: OrcaTheme.textSecondary,
                    ),
                  ),
                ],
              ],
            ),
            if (source != null) ...[
              const SizedBox(height: 6),
              Text(
                time != null ? '$source · $time' : source!,
                style: const TextStyle(
                  fontSize: 10,
                  color: OrcaTheme.textMuted,
                  fontWeight: FontWeight.w500,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
