import '../../../../core/cache/staleness.dart';

/// Variable measurement item with provenance.
class VariableItem {
  final String key;
  final double? value;
  final String unit;
  final double? threshold;
  final String status;
  final String source;
  final String time;
  final String? direction;

  const VariableItem({
    required this.key,
    required this.value,
    required this.unit,
    this.threshold,
    required this.status,
    required this.source,
    required this.time,
    this.direction,
  });
}

/// Hourly point for fl_chart forecast.
class HourlyPoint {
  final String hour;
  final double waveM;
  final double windKn;
  final String state;

  const HourlyPoint({
    required this.hour,
    required this.waveM,
    required this.windKn,
    required this.state,
  });
}

/// Safe window departure duration.
class SafeWindow {
  final String from;
  final String to;
  final bool isSafe;
  final double? hoursRemaining;

  const SafeWindow({
    required this.from,
    required this.to,
    required this.isSafe,
    this.hoursRemaining,
  });
}

/// Domain entity for Skipper Advisory (§4, §6).
class AdvisoryEntity {
  final String verdict; // go, caution, no_go
  final String colorHex;
  final String headline;
  final String? headlineHi;
  final List<String> plainEn;
  final List<String> plainHi;
  final SafeWindow? safeWindow;
  final Map<String, VariableItem> variables;
  final List<HourlyPoint> hourlyChart;
  final List<String> sources;
  final List<String> sourcesFailed;
  final int knownSources;
  final int totalSources;
  final DateTime timestamp;
  final StalenessInfo staleness;

  const AdvisoryEntity({
    required this.verdict,
    required this.colorHex,
    required this.headline,
    this.headlineHi,
    required this.plainEn,
    required this.plainHi,
    this.safeWindow,
    required this.variables,
    required this.hourlyChart,
    required this.sources,
    required this.sourcesFailed,
    required this.knownSources,
    required this.totalSources,
    required this.timestamp,
    required this.staleness,
  });
}
