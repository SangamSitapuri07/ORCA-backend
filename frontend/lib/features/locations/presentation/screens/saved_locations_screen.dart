import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../providers/locations_provider.dart';

class SavedLocationsScreen extends ConsumerWidget {
  const SavedLocationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final locations = ref.watch(savedLocationsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'MY PLACES',
          style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.2),
        ),
        backgroundColor: OrcaTheme.surface,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Saved Fishing Spots & Harbours',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 4),
            const Text(
              'Session only — Supabase persistence is unavailable.',
              style: TextStyle(
                fontSize: 13,
                color: VerdictColors.caution,
              ),
            ),
            const SizedBox(height: 16),

            if (locations.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 36),
                child: Center(
                  child: Text('No places saved in this session.', style: TextStyle(color: OrcaTheme.textSecondary)),
                ),
              ),
            for (final loc in locations) ...[
              Card(
                color: OrcaTheme.surface,
                margin: const EdgeInsets.only(bottom: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: BorderSide(
                    color: loc.isFavourite ? VerdictColors.go : Colors.white12,
                    width: loc.isFavourite ? 1.5 : 1.0,
                  ),
                ),
                child: ListTile(
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  leading: CircleAvatar(
                    backgroundColor: loc.category == 'Harbour' ? Colors.blue.withAlpha(50) : VerdictColors.go.withAlpha(50),
                    child: Icon(
                      loc.category == 'Harbour' ? Icons.anchor : Icons.phishing,
                      color: loc.category == 'Harbour' ? Colors.blue : VerdictColors.go,
                    ),
                  ),
                  title: Row(
                    children: [
                      Text(
                        loc.name,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      if (loc.isFavourite) ...[
                        const SizedBox(width: 6),
                        const Icon(Icons.star, color: Colors.amber, size: 16),
                      ],
                    ],
                  ),
                  subtitle: Text(
                    '${loc.latitude.toStringAsFixed(2)}° N, ${loc.longitude.toStringAsFixed(2)}° E • ${loc.category}',
                    style: const TextStyle(color: OrcaTheme.textSecondary, fontSize: 12),
                  ),
                  trailing: IconButton(
                    icon: Icon(
                      loc.isFavourite ? Icons.star : Icons.star_border,
                      color: loc.isFavourite ? Colors.amber : Colors.grey,
                    ),
                    onPressed: () {
                      ref.read(savedLocationsProvider.notifier).toggleFavourite(loc.id);
                    },
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _showAddLocationDialog(context, ref),
        icon: const Icon(Icons.add_location_alt),
        label: const Text('Add Spot'),
        backgroundColor: OrcaTheme.accent,
        foregroundColor: Colors.black,
      ),
    );
  }

  void _showAddLocationDialog(BuildContext context, WidgetRef ref) {
    final nameCtrl = TextEditingController();
    final latCtrl = TextEditingController(text: '20.80');
    final lonCtrl = TextEditingController(text: '70.30');
    const String selectedCategory = 'Fishing Area';

    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: OrcaTheme.surface,
        title: const Text('Save New Spot', style: TextStyle(color: Colors.white)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameCtrl,
              decoration: const InputDecoration(
                labelText: 'Spot Name',
                hintText: 'e.g. South Fishing Zone',
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: latCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Lat'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: lonCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(labelText: 'Lon'),
                  ),
                ),
              ],
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
          ),
          ElevatedButton(
            onPressed: () {
              if (nameCtrl.text.isNotEmpty) {
                final lat = double.tryParse(latCtrl.text) ?? 20.8;
                final lon = double.tryParse(lonCtrl.text) ?? 70.3;
                ref.read(savedLocationsProvider.notifier).addLocation(nameCtrl.text, lat, lon, selectedCategory);
                Navigator.pop(ctx);
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: OrcaTheme.accent, foregroundColor: Colors.black),
            child: const Text('Save Spot'),
          ),
        ],
      ),
    );
  }
}
