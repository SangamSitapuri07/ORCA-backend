import 'package:flutter/material.dart';
import '../theme/verdict_colors.dart';

/// Freshness state of an observation or cached payload (§7, §14).
enum StalenessState {
  fresh, // < 30 min
  recent, // 30 min - 3 hours
  stale, // > 3 hours
  unreachable,
}

/// Helper model for calculating staleness metadata.
class StalenessInfo {
  final StalenessState state;
  final Duration age;
  final DateTime fetchedAt;

  const StalenessInfo({
    required this.state,
    required this.age,
    required this.fetchedAt,
  });

  /// Computes staleness from fetch timestamp.
  factory StalenessInfo.fromDateTime(DateTime fetchedAt) {
    final now = DateTime.now();
    final age = now.difference(fetchedAt);

    StalenessState state;
    if (age.inMinutes < 30) {
      state = StalenessState.fresh;
    } else if (age.inHours < 3) {
      state = StalenessState.recent;
    } else {
      state = StalenessState.stale;
    }

    return StalenessInfo(
      state: state,
      age: age,
      fetchedAt: fetchedAt,
    );
  }

  /// Badge label for UI display.
  String get label {
    switch (state) {
      case StalenessState.fresh:
        return 'Fresh (<30m)';
      case StalenessState.recent:
        return 'Recent (${age.inMinutes}m ago)';
      case StalenessState.stale:
        return 'Stale (${age.inHours}h ago)';
      case StalenessState.unreachable:
        return 'Unreachable';
    }
  }

  /// Badge color according to design system tokens (§15).
  Color get color {
    switch (state) {
      case StalenessState.fresh:
        return VerdictColors.go;
      case StalenessState.recent:
        return VerdictColors.caution;
      case StalenessState.stale:
        return VerdictColors.stale;
      case StalenessState.unreachable:
        return VerdictColors.critical;
    }
  }
}
