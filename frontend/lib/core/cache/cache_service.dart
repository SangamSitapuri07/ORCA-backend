import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'staleness.dart';

/// Container for cached payload + timestamp metadata (§14).
class CachedRecord {
  final Map<String, dynamic> data;
  final DateTime fetchedAt;
  final Duration ttl;

  CachedRecord({
    required this.data,
    required this.fetchedAt,
    required this.ttl,
  });

  bool get isExpired => DateTime.now().difference(fetchedAt) > ttl;

  StalenessInfo get staleness => StalenessInfo.fromDateTime(fetchedAt);

  Map<String, dynamic> toJson() => {
        'data': data,
        'fetched_at': fetchedAt.toIso8601String(),
        'ttl_seconds': ttl.inSeconds,
      };

  factory CachedRecord.fromJson(Map<String, dynamic> json) {
    return CachedRecord(
      data: Map<String, dynamic>.from(json['data'] as Map),
      fetchedAt: DateTime.parse(json['fetched_at'] as String),
      ttl: Duration(seconds: json['ttl_seconds'] as int? ?? 1800),
    );
  }
}

/// Hive-backed cache service.
class CacheService {
  static const String defaultBoxName = 'orca_cache_box';
  Box<String>? _box;
  final Map<String, String> _memoryFallback = {};

  Future<void> init() async {
    try {
      if (!kIsWeb) {
        await Hive.initFlutter();
      }
      _box = await Hive.openBox<String>(defaultBoxName);
    } catch (e) {
      debugPrint('[CacheService] Hive init fallback to in-memory: $e');
    }
  }

  /// Saves a JSON record with current timestamp and TTL.
  Future<void> put(String key, Map<String, dynamic> data, {Duration ttl = const Duration(minutes: 30)}) async {
    final record = CachedRecord(
      data: data,
      fetchedAt: DateTime.now(),
      ttl: ttl,
    );
    final serialized = jsonEncode(record.toJson());
    if (_box != null && _box!.isOpen) {
      await _box!.put(key, serialized);
    } else {
      _memoryFallback[key] = serialized;
    }
  }

  /// Retrieves cached record for [key] if exists.
  CachedRecord? get(String key) {
    String? raw;
    if (_box != null && _box!.isOpen) {
      raw = _box!.get(key);
    } else {
      raw = _memoryFallback[key];
    }
    if (raw == null) return null;
    try {
      final json = jsonDecode(raw) as Map<String, dynamic>;
      return CachedRecord.fromJson(json);
    } catch (e) {
      debugPrint('[CacheService] Failed decoding cached record for key $key: $e');
      return null;
    }
  }

  /// Stores data in cache (convenience alias for put).
  Future<void> set(String key, Map<String, dynamic> data, {Duration ttl = const Duration(days: 3650)}) async {
    await put(key, data, ttl: ttl);
  }

  /// Removes a single key from cache.
  Future<void> remove(String key) async {
    if (_box != null && _box!.isOpen) {
      await _box!.delete(key);
    }
    _memoryFallback.remove(key);
  }

  /// Clears all entries in the cache.
  Future<void> clearAll() async {
    if (_box != null && _box!.isOpen) {
      await _box!.clear();
    }
    _memoryFallback.clear();
  }

  /// Returns total number of cached keys.
  int get keyCount {
    if (_box != null && _box!.isOpen) {
      return _box!.length;
    }
    return _memoryFallback.length;
  }
}

/// Global provider for cache service.
final cacheServiceProvider = Provider<CacheService>((ref) {
  return CacheService();
});
