import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../domain/entities/advisory.dart';

/// 48-Hour Wave Height & Wind Forecast Chart using fl_chart (§8, §9).
class HourlyChart extends StatelessWidget {
  final List<HourlyPoint> hourlyPoints;

  const HourlyChart({
    super.key,
    required this.hourlyPoints,
  });

  @override
  Widget build(BuildContext context) {
    if (hourlyPoints.isEmpty) {
      return const SizedBox.shrink();
    }

    final waveSpots = <FlSpot>[];
    final windSpots = <FlSpot>[];

    for (int i = 0; i < hourlyPoints.length; i++) {
      waveSpots.add(FlSpot(i.toDouble(), hourlyPoints[i].waveM));
      // scale wind to chart display (divide by 10 for dual display)
      windSpots.add(FlSpot(i.toDouble(), hourlyPoints[i].windKn / 10.0));
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: OrcaTheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: OrcaTheme.cardBorder, width: 1.0),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'HOURLY WAVE & WIND TREND',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  color: OrcaTheme.textSecondary,
                  letterSpacing: 0.8,
                ),
              ),
              Row(
                children: [
                  _legendItem('Wave (m)', VerdictColors.info),
                  const SizedBox(width: 12),
                  _legendItem('Wind (×10 kn)', VerdictColors.caution),
                ],
              ),
            ],
          ),
          const SizedBox(height: 18),
          SizedBox(
            height: 160,
            child: LineChart(
              LineChartData(
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: 1.0,
                  getDrawingHorizontalLine: (value) {
                    if (value == 2.5) {
                      // Caution Threshold Line
                      return const FlLine(
                        color: VerdictColors.caution,
                        strokeWidth: 1.5,
                        dashArray: [4, 4],
                      );
                    }
                    return FlLine(
                      color: Colors.white10,
                      strokeWidth: 1.0,
                    );
                  },
                ),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 28,
                      interval: 1.0,
                      getTitlesWidget: (value, meta) {
                        return Text(
                          '${value.toInt()}m',
                          style: const TextStyle(fontSize: 10, color: OrcaTheme.textMuted),
                        );
                      },
                    ),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 22,
                      interval: 2,
                      getTitlesWidget: (value, meta) {
                        final index = value.toInt();
                        if (index >= 0 && index < hourlyPoints.length) {
                          return Text(
                            hourlyPoints[index].hour,
                            style: const TextStyle(fontSize: 9, color: OrcaTheme.textSecondary),
                          );
                        }
                        return const SizedBox.shrink();
                      },
                    ),
                  ),
                ),
                borderData: FlBorderData(show: false),
                minX: 0,
                maxX: (hourlyPoints.length - 1).toDouble(),
                minY: 0,
                maxY: 4.5,
                lineBarsData: [
                  // Wave Height Line
                  LineChartBarData(
                    spots: waveSpots,
                    isCurved: true,
                    color: VerdictColors.info,
                    barWidth: 2.5,
                    isStrokeCapRound: true,
                    dotData: const FlDotData(show: false),
                    belowBarData: BarAreaData(
                      show: true,
                      color: VerdictColors.info.withValues(alpha: 0.12),
                    ),
                  ),
                  // Wind Speed Line
                  LineChartBarData(
                    spots: windSpots,
                    isCurved: true,
                    color: VerdictColors.caution,
                    barWidth: 2.0,
                    dashArray: const [3, 3],
                    isStrokeCapRound: true,
                    dotData: const FlDotData(show: false),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Row(
            children: [
              Icon(Icons.info_outline, size: 12, color: VerdictColors.caution),
              SizedBox(width: 4),
              Text(
                'Dashed yellow line indicates 2.5m small-craft caution threshold',
                style: TextStyle(fontSize: 10, color: OrcaTheme.textMuted),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _legendItem(String text, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 4),
        Text(
          text,
          style: const TextStyle(fontSize: 10, color: OrcaTheme.textSecondary),
        ),
      ],
    );
  }
}
