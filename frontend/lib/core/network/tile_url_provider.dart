import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../config/api_paths.dart';
import 'dio_provider.dart';

/// First-party OSM tile-proxy template derived from the configured ORCA Box.
/// Presentation widgets never embed or call the public tile host directly.
final orcaTileUrlProvider = Provider<String?>((ref) {
  final rawBase = ref.watch(baseUrlProvider).trim();
  if (rawBase.isEmpty) return null;
  final base = rawBase.endsWith('/')
      ? rawBase.substring(0, rawBase.length - 1)
      : rawBase;
  return '$base${ApiPaths.tileTemplate}';
});
