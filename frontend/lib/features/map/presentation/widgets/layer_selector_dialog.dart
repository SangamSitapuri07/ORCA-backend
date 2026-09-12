import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../domain/entities/zone_snapshot.dart';
import '../providers/map_provider.dart';

/// Modal dialog allowing skippers/judges to toggle map raster & vector layers (§8).
class LayerSelectorDialog extends ConsumerWidget {
  const LayerSelectorDialog({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final layers = ref.watch(mapLayersProvider);

    return AlertDialog(
      backgroundColor: OrcaTheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: OrcaTheme.cardBorder),
      ),
      title: const Row(
        children: [
          Icon(Icons.layers, color: OrcaTheme.accent, size: 22),
          SizedBox(width: 8),
          Text(
            'Map Data Layers',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
          ),
        ],
      ),
      content: SizedBox(
        width: double.maxFinite,
        child: ListView.separated(
          shrinkWrap: true,
          itemCount: layers.length,
          separatorBuilder: (context, index) => const Divider(color: OrcaTheme.cardBorder, height: 1),
          itemBuilder: (context, index) {
            final layer = layers[index];
            return SwitchListTile(
              title: Text(
                layer.name,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: Colors.white,
                ),
              ),
              subtitle: Text(
                layer.source,
                style: const TextStyle(fontSize: 11, color: OrcaTheme.textMuted),
              ),
              value: layer.isEnabled,
              activeThumbColor: OrcaTheme.accent,
              onChanged: (bool val) {
                final updated = List<MapLayerEntity>.from(layers);
                updated[index] = layer.copyWith(isEnabled: val);
                ref.read(mapLayersProvider.notifier).state = updated;
              },
            );
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Done', style: TextStyle(color: OrcaTheme.accent, fontWeight: FontWeight.bold)),
        ),
      ],
    );
  }
}
