import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../domain/entities/route_advisory.dart';

/// Strip listing 30km sampled points along the transit (§4, §6).
class TransitPointsStrip extends StatelessWidget {
  final List<TransitPoint> points;

  const TransitPointsStrip({
    super.key,
    required this.points,
  });

  @override
  Widget build(BuildContext context) {
    if (points.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          child: Text(
            'TRANSIT WAYPOINTS & SAMPLING (EVERY ~30 KM)',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              color: OrcaTheme.textSecondary,
              letterSpacing: 0.8,
            ),
          ),
        ),
        const SizedBox(height: 4),
        ...points.map((pt) {
          final color = VerdictColors.fromVerdict(pt.state);

          return Container(
            padding: const EdgeInsets.all(12),
            margin: const EdgeInsets.symmetric(vertical: 4),
            decoration: BoxDecoration(
              color: OrcaTheme.surface,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: pt.state != 'good' ? color.withValues(alpha: 0.6) : OrcaTheme.cardBorder,
                width: 1.0,
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Distance badge
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: OrcaTheme.surfaceElevated,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '${pt.sailKm.toStringAsFixed(0)} km',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: OrcaTheme.accent,
                    ),
                  ),
                ),
                const SizedBox(width: 12),

                // Conditions and reason
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Wave: ${pt.waveM?.toStringAsFixed(1) ?? "--"}m · Wind: ${pt.windKn?.toStringAsFixed(1) ?? "--"}kn',
                            style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: color.withValues(alpha: 0.2),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              pt.state.toUpperCase(),
                              style: TextStyle(
                                color: color,
                                fontSize: 9.5,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        pt.why,
                        style: const TextStyle(
                          fontSize: 11.5,
                          color: OrcaTheme.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        }),
      ],
    );
  }
}
