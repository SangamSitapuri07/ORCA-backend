import 'package:flutter/material.dart';
import '../theme/verdict_colors.dart';

/// Renders a shape + icon + colour verdict badge for low-literacy clarity (§7).
class VerdictBadge extends StatelessWidget {
  final String verdict;
  final double size;
  final bool showLabel;

  const VerdictBadge({
    super.key,
    required this.verdict,
    this.size = 28.0,
    this.showLabel = true,
  });

  @override
  Widget build(BuildContext context) {
    final color = VerdictColors.fromVerdict(verdict);
    final iconData = VerdictColors.iconForVerdict(verdict);
    final label = _formatVerdictLabel(verdict);

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: showLabel ? 10 : 6,
        vertical: 4,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.8), width: 1.2),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(
            iconData,
            color: color,
            size: size * 0.8,
          ),
          if (showLabel) ...[
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w800,
                fontSize: size * 0.5,
                letterSpacing: 0.6,
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _formatVerdictLabel(String v) {
    final lower = v.toLowerCase().replaceAll('-', '_');
    if (lower.contains('go') && !lower.contains('no_go') && !lower.contains('nogo')) {
      return 'GO SAFE';
    }
    if (lower.contains('caution') || lower.contains('mod')) {
      return 'CAUTION';
    }
    if (lower.contains('no_go') || lower.contains('nogo') || lower.contains('danger')) {
      return 'NO-GO';
    }
    return v.toUpperCase();
  }
}
