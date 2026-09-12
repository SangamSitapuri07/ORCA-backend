import 'package:flutter/material.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/staleness_badge.dart';
import '../../domain/entities/advisory.dart';

/// Primary skipper safety verdict card (§6, §7, §26A).
class VerdictCard extends StatelessWidget {
  final AdvisoryEntity advisory;

  const VerdictCard({
    super.key,
    required this.advisory,
  });

  @override
  Widget build(BuildContext context) {
    final verdictColor = VerdictColors.fromVerdict(advisory.verdict);
    final verdictBg = VerdictColors.backgroundFromVerdict(advisory.verdict);
    final verdictIcon = VerdictColors.iconForVerdict(advisory.verdict);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: verdictBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: verdictColor, width: 2.0),
        boxShadow: [
          BoxShadow(
            color: verdictColor.withValues(alpha: 0.2),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: Icon + Verdict Label + Staleness Badge
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: verdictColor.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      verdictIcon,
                      color: verdictColor,
                      size: 32,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'CAN I GO OUT?',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: Colors.white70,
                          letterSpacing: 1.0,
                        ),
                      ),
                      Text(
                        _verdictText(advisory.verdict),
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w900,
                          color: verdictColor,
                          letterSpacing: 0.8,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              StalenessBadge(staleness: advisory.staleness),
            ],
          ),
          const SizedBox(height: 14),

          // Primary English Headline
          Text(
            advisory.headline,
            style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: Colors.white,
              height: 1.3,
            ),
          ),

          // Secondary Hindi/Bilingual Headline if present
          if (advisory.headlineHi != null && advisory.headlineHi!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              advisory.headlineHi!,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: Colors.white.withValues(alpha: 0.85),
                height: 1.3,
              ),
            ),
          ],

          const SizedBox(height: 14),
          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 10),

          // Plain Language Bullet Points (§7)
          ...advisory.plainEn.take(3).map(
                (bullet) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Icon(Icons.circle, size: 6, color: verdictColor),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          bullet,
                          style: const TextStyle(
                            fontSize: 12.5,
                            color: Colors.white70,
                            height: 1.3,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
        ],
      ),
    );
  }

  String _verdictText(String v) {
    final lower = v.toLowerCase().replaceAll('-', '_');
    if (lower.contains('go') && !lower.contains('no_go') && !lower.contains('nogo')) {
      return 'GO SAFE ✔';
    }
    if (lower.contains('caution') || lower.contains('mod')) {
      return 'CAUTION ⚠';
    }
    if (lower.contains('no_go') || lower.contains('nogo') || lower.contains('danger')) {
      return 'NO-GO ⛔';
    }
    return v.toUpperCase();
  }
}
