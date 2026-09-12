import 'package:flutter/material.dart';
import '../theme/orca_theme.dart';

/// App-wide footer displaying provenance and observation sources (§7, §15).
class SourceFooter extends StatelessWidget {
  final List<String> sources;
  final String? timeLabel;

  const SourceFooter({
    super.key,
    required this.sources,
    this.timeLabel,
  });

  @override
  Widget build(BuildContext context) {
    if (sources.isEmpty) {
      return const SizedBox.shrink();
    }

    final joinedSources = sources.join(' · ');
    final fullText = timeLabel != null && timeLabel!.isNotEmpty
        ? '$joinedSources · $timeLabel'
        : joinedSources;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      margin: const EdgeInsets.only(top: 8, bottom: 4),
      decoration: BoxDecoration(
        color: OrcaTheme.surface.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: OrcaTheme.cardBorder.withValues(alpha: 0.4), width: 0.8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const Icon(
            Icons.verified_outlined,
            size: 14,
            color: OrcaTheme.textMuted,
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              fullText,
              style: const TextStyle(
                fontSize: 11,
                color: OrcaTheme.textMuted,
                fontWeight: FontWeight.w500,
                letterSpacing: 0.2,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
