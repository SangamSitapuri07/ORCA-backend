import 'package:flutter/material.dart';
import '../../../../core/network/source_catalog.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../providers/settings_provider.dart';

/// Renders the complete source health table generated from SourceCatalog.
class SourceCatalogHealthView extends StatelessWidget {
  final Map<String, SourceHealthItem> liveSources;

  const SourceCatalogHealthView({
    super.key,
    required this.liveSources,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '${SourceCatalog.all.length} DATA SOURCES (CONFIGURATION STATUS)',
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                color: OrcaTheme.textSecondary,
                letterSpacing: 0.8,
              ),
            ),
            Text(
              '${liveSources.length}/${SourceCatalog.all.length} reported',
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.bold,
                color: OrcaTheme.accent,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),

        // Every source in the authoritative Phase-1 catalog.
        ...SourceCatalog.all.map((source) {
          final live = liveSources[source.healthKey];
          final status = live?.status ?? 'not_reported';
          final latency = live?.latencyMs;
          final note = live?.note ?? 'ORCA Box did not report this source.';

          final statusColor = _statusColor(status);

          return Container(
            padding: const EdgeInsets.all(12),
            margin: const EdgeInsets.symmetric(vertical: 4),
            decoration: BoxDecoration(
              color: OrcaTheme.surface,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: status != 'online' ? statusColor.withValues(alpha: 0.5) : OrcaTheme.cardBorder,
                width: 1.0,
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Status icon dot
                Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
                const SizedBox(width: 10),

                // Source details
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Text(
                              source.name,
                              style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: statusColor.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              status.toUpperCase().replaceAll('_', ' '),
                              style: TextStyle(
                                color: statusColor,
                                fontSize: 9.5,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${source.agency} · ${source.host}',
                        style: const TextStyle(
                          fontSize: 10.5,
                          color: OrcaTheme.textMuted,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        note,
                        style: const TextStyle(
                          fontSize: 11,
                          color: OrcaTheme.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),

                // Latency
                Text(
                  latency == null ? '--' : '${latency}ms',
                  style: const TextStyle(
                    fontSize: 10,
                    color: OrcaTheme.textMuted,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          );
        }),
      ],
    );
  }

  Color _statusColor(String status) {
    switch (status.toLowerCase()) {
      case 'online':
      case 'ok':
        return VerdictColors.go;
      case 'available':
      case 'configured':
        return VerdictColors.info;
      case 'degraded':
        return VerdictColors.caution;
      case 'offline':
      case 'failed':
      case 'unreachable':
      case 'unavailable':
      case 'disabled':
        return VerdictColors.critical;
      default:
        return VerdictColors.stale;
    }
  }
}
