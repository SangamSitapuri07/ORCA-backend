import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/utils/geo_utils.dart';
import '../../../../core/widgets/source_footer.dart';
import '../../../../core/widgets/stat_tile.dart';
import '../../domain/entities/zone_snapshot.dart';

/// Bottom Sheet Card displayed when a fisherman taps a map location (§4, §8).
class ProbeBottomSheet extends StatelessWidget {
  final ZoneSnapshot snapshot;
  final VoidCallback onClose;

  const ProbeBottomSheet({
    super.key,
    required this.snapshot,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.78,
      ),
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(
        color: OrcaTheme.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        boxShadow: [
          BoxShadow(
            color: Colors.black45,
            blurRadius: 16,
            offset: Offset(0, -4),
          ),
        ],
      ),
      child: SingleChildScrollView(
        child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Drag handle
          Center(
            child: Container(
              width: 36,
              height: 4,
              margin: const EdgeInsets.only(bottom: 12),
              decoration: BoxDecoration(
                color: OrcaTheme.textMuted.withValues(alpha: 0.5),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),

          // Header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    snapshot.zoneName,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    snapshot.offshoreDistKm == null
                        ? GeoUtils.formatCoordinate(snapshot.lat, snapshot.lon)
                        : '${GeoUtils.formatCoordinate(snapshot.lat, snapshot.lon)} · ${snapshot.offshoreDistKm!.toStringAsFixed(1)} km offshore',
                    style: const TextStyle(
                      fontSize: 12,
                      color: OrcaTheme.textSecondary,
                    ),
                  ),
                ],
              ),
              IconButton(
                icon: const Icon(Icons.close, color: OrcaTheme.textSecondary, size: 20),
                onPressed: onClose,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Grid of spot variables
          GridView.count(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisCount: 3,
            mainAxisSpacing: 8,
            crossAxisSpacing: 8,
            childAspectRatio: 1.15,
            children: [
              StatTile(
                label: 'Wave Height',
                value: Formatters.waveHeight(snapshot.waveHeightM),
                icon: Icons.waves,
                status: snapshot.waveHeightM == null ? 'unavailable' : null,
              ),
              StatTile(
                label: 'Wind Speed',
                value: Formatters.windKnots(snapshot.windSpeedKn),
                icon: Icons.air,
                status: snapshot.windSpeedKn == null ? 'unavailable' : null,
              ),
              StatTile(
                label: 'Sea Temp Avg',
                value: Formatters.temperature(snapshot.seaTempC),
                icon: Icons.thermostat,
                status: snapshot.seaTempC == null ? 'unavailable' : null,
              ),
              StatTile(
                label: 'Current',
                value: Formatters.current(snapshot.currentSpeedKn, snapshot.currentDirection),
                icon: Icons.navigation,
                status: snapshot.currentSpeedKn == null ? 'unavailable' : null,
              ),
              StatTile(
                label: 'Chlorophyll',
                value: snapshot.chlorophyllMgM3 != null
                    ? Formatters.chlorophyll(snapshot.chlorophyllMgM3)
                    : 'N/A',
                icon: Icons.biotech,
                status: snapshot.chlorophyllMgM3 == null ? 'unavailable' : null,
              ),
              StatTile(
                label: 'Fishing Activity',
                value: snapshot.fishingEffortHours != null
                    ? Formatters.fishingEffort(snapshot.fishingEffortHours)
                    : '--',
                icon: Icons.sailing,
                status: snapshot.fishingEffortHours == null ? 'unavailable' : null,
              ),
            ],
          ),

          if (snapshot.observations.isNotEmpty) ...[
            const SizedBox(height: 8),
            Theme(
              data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                tilePadding: EdgeInsets.zero,
                childrenPadding: EdgeInsets.zero,
                leading: const Icon(Icons.info_outline, size: 18, color: VerdictColors.info),
                title: const Text(
                  'Observation details',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: OrcaTheme.textPrimary,
                  ),
                ),
                subtitle: const Text(
                  'Source and observation time',
                  style: TextStyle(fontSize: 10, color: OrcaTheme.textMuted),
                ),
                children: snapshot.observations.entries.map((entry) {
                  final metadata = entry.value;
                  final details = <String>[
                    metadata.source,
                    metadata.timeLabel,
                    if (metadata.statistic != null) metadata.statistic!,
                    if (metadata.note != null) metadata.note!,
                  ];
                  return Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(bottom: 6),
                    padding: const EdgeInsets.all(9),
                    decoration: BoxDecoration(
                      color: OrcaTheme.surfaceElevated,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _observationLabel(entry.key),
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            color: OrcaTheme.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          details.join('\n'),
                          style: const TextStyle(
                            fontSize: 10,
                            height: 1.35,
                            color: OrcaTheme.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          ],

          if (snapshot.sourcesFailed.isNotEmpty) ...[
            const SizedBox(height: 6),
            Theme(
              data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                tilePadding: EdgeInsets.zero,
                childrenPadding: const EdgeInsets.only(bottom: 8),
                leading: const Icon(
                  Icons.warning_amber_rounded,
                  size: 18,
                  color: VerdictColors.caution,
                ),
                title: Text(
                  '${snapshot.sourcesFailed.length} unavailable check(s)',
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: OrcaTheme.textPrimary,
                  ),
                ),
                subtitle: const Text(
                  'Tap for exact provider errors',
                  style: TextStyle(fontSize: 10, color: OrcaTheme.textMuted),
                ),
                children: snapshot.sourcesFailed.map((failure) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 5),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        '• $failure',
                        style: const TextStyle(
                          fontSize: 10,
                          color: OrcaTheme.textSecondary,
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ],

          if (snapshot.nearestHarbour != null) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: OrcaTheme.surfaceElevated,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  const Icon(Icons.anchor, size: 16, color: VerdictColors.info),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Nearest Harbour: ${snapshot.nearestHarbour} (${snapshot.nearestHarbourDistKm?.toStringAsFixed(1) ?? "--"} km)',
                      style: const TextStyle(
                        fontSize: 11.5,
                        color: OrcaTheme.textPrimary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],

          const SizedBox(height: 10),
          SourceFooter(
            sources: snapshot.sources,
            timeLabel: 'Retrieved ${DateFormatter.formatIstDateTime(snapshot.timestamp)}',
          ),
        ],
        ),
      ),
    );
  }

  String _observationLabel(String key) {
    switch (key) {
      case 'wave_height_m':
        return 'Wave height';
      case 'wind_speed_kn':
        return 'Wind speed';
      case 'sea_temp_c':
        return 'Sea temperature';
      case 'current_speed_kn':
        return 'Surface current';
      case 'chlorophyll_mg_m3':
        return 'Chlorophyll';
      case 'fishing_effort_hours':
        return 'Reported fishing activity';
      default:
        return key.replaceAll('_', ' ');
    }
  }
}
