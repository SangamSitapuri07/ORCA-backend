import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/utils/formatters.dart';
import '../../../../core/widgets/stat_tile.dart';
import '../../domain/entities/advisory.dart';

/// Grid of marine variables with source and status badges (§8).
class VariablesGrid extends StatelessWidget {
  final Map<String, VariableItem> variables;

  const VariablesGrid({
    super.key,
    required this.variables,
  });

  @override
  Widget build(BuildContext context) {
    final wave = variables['wave_height'];
    final wind = variables['wind_speed'];
    final gusts = variables['wind_gusts'];
    final sst = variables['sea_surface_temp'];
    final current = variables['ocean_current'];
    final chl = variables['chlorophyll'];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          child: Text(
            'KEY OCEAN CONDITIONS',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: OrcaTheme.textSecondary,
              letterSpacing: 0.8,
            ),
          ),
        ),
        const SizedBox(height: 4),
        GridView.count(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisCount: 2,
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          childAspectRatio: 1.35,
          children: [
            StatTile(
              label: 'Wave Height',
              value: wave?.value != null ? '${wave!.value!.toStringAsFixed(1)}' : '--',
              unit: 'm',
              icon: Icons.waves,
              status: wave?.status,
              source: wave?.source ?? 'Unavailable',
              time: wave?.time,
            ),
            StatTile(
              label: 'Sustained Wind',
              value: wind?.value != null ? '${wind!.value!.toStringAsFixed(1)}' : '--',
              unit: 'kn',
              icon: Icons.air,
              status: wind?.status,
              source: wind?.source ?? 'Unavailable',
              time: wind?.time,
            ),
            StatTile(
              label: 'Wind Gusts',
              value: gusts?.value != null ? '${gusts!.value!.toStringAsFixed(1)}' : '--',
              unit: 'kn',
              icon: Icons.storm,
              status: gusts?.status,
              source: gusts?.source ?? 'Unavailable',
              time: gusts?.time,
            ),
            StatTile(
              label: 'Sea Surface Temp',
              value: sst?.value != null ? '${sst!.value!.toStringAsFixed(1)}' : '--',
              unit: '°C',
              icon: Icons.thermostat,
              status: sst?.status,
              source: sst?.source ?? 'Unavailable',
              time: sst?.time,
            ),
            StatTile(
              label: 'Surface Current',
              value: current?.value != null ? '${current!.value!.toStringAsFixed(1)}' : '--',
              unit: current?.direction != null ? 'kn ${current!.direction}' : 'kn',
              icon: Icons.navigation,
              status: current?.status,
              source: current?.source ?? 'Unavailable',
              time: current?.time,
            ),
            StatTile(
              label: 'Chlorophyll-a',
              value: chl?.value != null ? '${chl!.value!.toStringAsFixed(2)}' : '--',
              unit: 'mg/m³',
              icon: Icons.biotech,
              status: chl?.status,
              source: chl?.source ?? 'Unavailable',
              time: chl?.time,
            ),
          ],
        ),
      ],
    );
  }
}
