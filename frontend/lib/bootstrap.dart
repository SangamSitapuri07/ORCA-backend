import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/cache/cache_service.dart';

/// Composition root for the Phase-1 Android client. Supabase is deliberately
/// absent until the team's authoritative Phase-2 repositories and auth policy
/// are supplied; core ORCA Box safety never depends on cloud initialization.
Future<ProviderContainer> bootstrap() async {
  WidgetsFlutterBinding.ensureInitialized();

  final cacheService = CacheService();
  await cacheService.init();

  return ProviderContainer(
    overrides: [
      cacheServiceProvider.overrideWithValue(cacheService),
    ],
  );
}
