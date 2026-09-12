import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/config/api_paths.dart';
import '../../../../core/network/dio_provider.dart';

class SourceHealthItem {
  final String key;
  final String name;
  final String agency;
  final String status;
  final int? latencyMs;
  final String note;

  const SourceHealthItem({
    required this.key,
    required this.name,
    required this.agency,
    required this.status,
    this.latencyMs,
    required this.note,
  });
}

class SystemHealthSnapshot {
  final String status;
  final String version;
  final String buildCommit;
  final int? uptimeSeconds;
  final Map<String, SourceHealthItem> dataSources;
  final int? cacheKeys;
  final double? cacheHitRate;
  final Map<String, dynamic> components;

  const SystemHealthSnapshot({
    required this.status,
    required this.version,
    required this.buildCommit,
    this.uptimeSeconds,
    required this.dataSources,
    this.cacheKeys,
    this.cacheHitRate,
    this.components = const <String, dynamic>{},
  });
}

class HealthNotifier extends StateNotifier<AsyncValue<SystemHealthSnapshot>> {
  final Ref _ref;

  HealthNotifier(this._ref) : super(const AsyncValue.loading()) {
    checkHealth();
  }

  Future<void> checkHealth() async {
    state = const AsyncValue.loading();
    try {
      final response = await _ref.read(dioProvider).get<Map<String, dynamic>>(ApiPaths.health);
      if (response.data == null) throw const FormatException('Empty health response');
      state = AsyncValue.data(_parseHealth(response.data!));
    } catch (error, stack) {
      // Never replace a failed ORCA Box health request with a healthy fixture.
      state = AsyncValue.error('ORCA Box health request failed: $error', stack);
    }
  }

  SystemHealthSnapshot _parseHealth(Map<String, dynamic> json) {
    final sources = <String, SourceHealthItem>{};
    final rawSources = json['source_health'];
    if (rawSources is Map) {
      rawSources.forEach((key, raw) {
        if (raw is! Map) return;
        final value = Map<String, dynamic>.from(raw);
        sources[key.toString()] = SourceHealthItem(
          key: key.toString(),
          name: value['name'] as String? ?? key.toString(),
          agency: value['agency'] as String? ?? '',
          status: value['status'] as String? ?? 'not_reported',
          latencyMs: (value['latency_ms'] as num?)?.toInt(),
          note: value['note'] as String? ?? 'No status note returned.',
        );
      });
    }

    final cache = json['cache_summary'] is Map
        ? Map<String, dynamic>.from(json['cache_summary'] as Map)
        : null;
    return SystemHealthSnapshot(
      status: json['status'] as String? ?? 'unknown',
      version: json['version'] as String? ?? 'unknown',
      buildCommit: json['build_commit'] as String? ?? 'unknown',
      uptimeSeconds: (json['uptime_seconds'] as num?)?.toInt(),
      dataSources: sources,
      cacheKeys: (cache?['in_memory_keys'] as num?)?.toInt(),
      cacheHitRate: (cache?['hit_rate_pct'] as num?)?.toDouble(),
      components: json['components'] is Map
          ? Map<String, dynamic>.from(json['components'] as Map)
          : const <String, dynamic>{},
    );
  }
}

final healthProvider = StateNotifierProvider<HealthNotifier, AsyncValue<SystemHealthSnapshot>>((ref) {
  return HealthNotifier(ref);
});

final selectedLocaleProvider = StateProvider<String>((ref) {
  return ref.watch(cacheServiceProvider).get('settings.locale')?.data['value'] as String? ?? 'en';
});
