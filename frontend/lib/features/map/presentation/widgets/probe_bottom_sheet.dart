import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/utils/geo_utils.dart';
import '../../../../core/widgets/source_footer.dart';
import '../../../../core/widgets/staleness_badge.dart';
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
              Row(
                children: [
                  StalenessBadge(staleness: snapshot.staleness),
                  IconButton(
                    icon: const Icon(Icons.close, color: OrcaTheme.textSecondary, size: 20),
                    onPressed: onClose,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
                ],
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
                status: snapshot.waveHeightM == null
                    ? 'unavailable'
                    : snapshot.waveHeightM! >= 2.5 ? 'caution' : 'good',
              ),
              StatTile(
                label: 'Wind Speed',
                value: Formatters.windKnots(snapshot.windSpeedKn),
                icon: Icons.air,
                status: snapshot.windSpeedKn == null
                    ? 'unavailable'
                    : snapshot.windSpeedKn! >= 20.0 ? 'caution' : 'good',
              ),
              StatTile(
                label: 'Sea Temp',
                value: Formatters.temperature(snapshot.seaTempC),
                icon: Icons.thermostat,
                status: snapshot.seaTempC == null ? 'unavailable' : 'good',
              ),
              StatTile(
                label: 'Current',
                value: Formatters.current(snapshot.currentSpeedKn, snapshot.currentDirection),
                icon: Icons.navigation,
                status: snapshot.currentSpeedKn == null
                    ? 'unavailable'
                    : snapshot.currentSpeedKn! > 3.0 ? 'caution' : 'good',
              ),
              StatTile(
                label: 'Chlorophyll',
                value: snapshot.chlorophyllMgM3 != null
                    ? Formatters.chlorophyll(snapshot.chlorophyllMgM3)
                    : 'N/A',
                icon: Icons.biotech,
                status: snapshot.chlorophyllMgM3 == null ? 'unavailable' : 'good',
              ),
              StatTile(
                label: 'Fleet Effort',
                value: snapshot.fishingEffortHours != null
                    ? Formatters.fishingEffort(snapshot.fishingEffortHours)
                    : '--',
                icon: Icons.sailing,
                status: snapshot.fishingEffortHours == null ? 'unavailable' : 'good',
              ),
            ],
          ),

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
            timeLabel: DateFormatter.formatIstTime(snapshot.timestamp),
          ),
        ],
      ),
    );
  }
}
