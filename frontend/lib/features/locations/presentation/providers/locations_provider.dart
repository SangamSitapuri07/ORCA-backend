import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/saved_location.dart';

/// Session-local saved places. Durable Phase-2 Supabase persistence is not
/// available, so no seeded or falsely synced records are exposed.
final savedLocationsProvider = StateNotifierProvider<SavedLocationsNotifier, List<SavedLocation>>((ref) {
  return SavedLocationsNotifier();
});

class SavedLocationsNotifier extends StateNotifier<List<SavedLocation>> {
  SavedLocationsNotifier() : super(const <SavedLocation>[]);

  void addLocation(String name, double lat, double lon, String category) {
    final location = SavedLocation(
      id: 'local-${DateTime.now().millisecondsSinceEpoch}',
      name: name,
      latitude: lat,
      longitude: lon,
      category: category,
      isFavourite: false,
      notes: 'Session only — cloud persistence unavailable',
    );
    state = [location, ...state];
  }

  void toggleFavourite(String id) {
    state = [
      for (final location in state)
        if (location.id == id)
          location.copyWith(isFavourite: !location.isFavourite)
        else
          location,
    ];
  }

  void deleteLocation(String id) {
    state = state.where((location) => location.id != id).toList();
  }
}
