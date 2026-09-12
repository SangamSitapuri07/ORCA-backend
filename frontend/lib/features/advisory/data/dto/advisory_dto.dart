import '../../domain/entities/advisory.dart';
import '../../../../core/cache/staleness.dart';
import '../../../../core/utils/date_formatter.dart';

/// DTO for the authoritative ORCA Box advisory contract.
class AdvisoryDto {
  final String verdict;
  final String? color;
  final String headline;
  final String? headlineHi;
  final List<String> plainEn;
  final List<String> plainHi;
  final Map<String, dynamic>? safeWindowJson;
  final Map<String, dynamic>? variablesJson;
  final dynamic hourlyChartJson;
  final List<String> sources;
  final List<String> sourcesFailed;
  final int knownSources;
  final int totalSources;
  final String? timestampStr;

  AdvisoryDto({
    required this.verdict,
    this.color,
    required this.headline,
    this.headlineHi,
    required this.plainEn,
    required this.plainHi,
    this.safeWindowJson,
    this.variablesJson,
    this.hourlyChartJson,
    required this.sources,
    required this.sourcesFailed,
    required this.knownSources,
    required this.totalSources,
    this.timestampStr,
  });

  static List<String> _strings(dynamic value) => value is List
      ? value.map((item) => item.toString()).toList()
      : <String>[];

  factory AdvisoryDto.fromJson(Map<String, dynamic> json) {
    final sources = _strings(json['sources']);
    final coverage = json['data_coverage'] is Map
        ? Map<String, dynamic>.from(json['data_coverage'] as Map)
        : null;
    final failed = _strings(json['sources_failed']).isNotEmpty
        ? _strings(json['sources_failed'])
        : _strings(coverage?['sources_failed']);
    final details = json['variable_details'] ?? json['variables'];

    return AdvisoryDto(
      verdict: json['verdict'] as String? ?? 'unknown',
      color: json['color'] as String?,
      headline: json['headline'] as String? ?? 'Advisory headline unavailable.',
      headlineHi: json['headline_hi'] as String?,
      plainEn: _strings(json['plain_en']),
      plainHi: _strings(json['plain_hi']),
      safeWindowJson: json['safe_window'] is Map
          ? Map<String, dynamic>.from(json['safe_window'] as Map)
          : null,
      variablesJson: details is Map ? Map<String, dynamic>.from(details) : null,
      hourlyChartJson: json['hourly_chart'],
      sources: sources,
      sourcesFailed: failed,
      knownSources: coverage?['known'] as int? ?? sources.length,
      totalSources: coverage?['total'] as int? ?? (sources.length + failed.length),
      timestampStr: (json['generated_at'] ?? json['timestamp']) as String?,
    );
  }

  DateTime? get parsedSourceTimestamp => DateFormatter.parseIso(timestampStr);

  DateTime get sourceTimestamp => parsedSourceTimestamp ??
      DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);

  String _colorHex() {
    final raw = color?.toLowerCase();
    if (raw != null && raw.startsWith('#')) return raw;
    switch (raw) {
      case 'green':
        return '#4ade80';
      case 'amber':
        return '#fbbf24';
      case 'red':
        return '#f87171';
      default:
        return '#94a3b8';
    }
  }

  AdvisoryEntity toEntity(StalenessInfo staleness) {
    final parsedVariables = <String, VariableItem>{};
    variablesJson?.forEach((key, value) {
      if (value is! Map) return;
      final item = Map<String, dynamic>.from(value);
      final observedAt = item['observed_at']?.toString();
      final observedFrom = item['observed_from']?.toString();
      final observedTo = item['observed_to']?.toString();
      final observationTime = observedAt != null && observedAt.isNotEmpty
          ? observedAt
          : observedFrom != null && observedTo != null
              ? '$observedFrom to $observedTo'
              : item['retrieved_at']?.toString() ?? item['time']?.toString() ?? 'Unavailable';
      parsedVariables[key] = VariableItem(
        key: key,
        value: (item['value'] as num?)?.toDouble(),
        unit: item['unit'] as String? ?? '',
        threshold: (item['threshold'] as num?)?.toDouble(),
        status: item['status'] as String? ?? 'unavailable',
        source: item['source'] as String? ?? 'Unavailable',
        time: observationTime,
        direction: item['direction'] as String?,
      );
    });

    final parsedHourly = <HourlyPoint>[];
    if (hourlyChartJson is List) {
      for (final raw in hourlyChartJson as List) {
        if (raw is! Map) continue;
        final item = Map<String, dynamic>.from(raw);
        final wave = (item['wave_m'] as num?)?.toDouble();
        final wind = (item['wind_kn'] as num?)?.toDouble();
        if (wave == null || wind == null) continue;
        parsedHourly.add(HourlyPoint(
          hour: item['hour'] as String? ?? '--',
          waveM: wave,
          windKn: wind,
          state: item['state'] as String? ?? 'unknown',
        ));
      }
    } else if (hourlyChartJson is Map) {
      final chart = Map<String, dynamic>.from(hourlyChartJson as Map);
      final labels = chart['labels'] is List ? chart['labels'] as List : const [];
      final waves = chart['wave_m'] is List ? chart['wave_m'] as List : const [];
      final winds = chart['wind_kn'] is List ? chart['wind_kn'] as List : const [];
      final states = chart['state'] is List ? chart['state'] as List : const [];
      final count = [labels.length, waves.length, winds.length].reduce((a, b) => a < b ? a : b);
      for (var index = 0; index < count; index++) {
        final wave = waves[index] is num ? (waves[index] as num).toDouble() : null;
        final wind = winds[index] is num ? (winds[index] as num).toDouble() : null;
        if (wave == null || wind == null) continue;
        parsedHourly.add(HourlyPoint(
          hour: labels[index].toString(),
          waveM: wave,
          windKn: wind,
          state: index < states.length && states[index] is String
              ? states[index] as String
              : 'unknown',
        ));
      }
    }

    SafeWindow? parsedSafeWindow;
    final safeWindow = safeWindowJson;
    if (safeWindow != null && (safeWindow['found'] == true || safeWindow['from'] != null)) {
      parsedSafeWindow = SafeWindow(
        from: (safeWindow['from_utc'] ?? safeWindow['from']) as String? ?? '',
        to: (safeWindow['to_utc'] ?? safeWindow['to']) as String? ?? '',
        isSafe: safeWindow['found'] as bool? ?? safeWindow['is_safe'] as bool? ?? false,
        hoursRemaining: (safeWindow['hours'] ?? safeWindow['hours_remaining']) is num
            ? ((safeWindow['hours'] ?? safeWindow['hours_remaining']) as num).toDouble()
            : null,
      );
    }

    final timestamp = sourceTimestamp;
    return AdvisoryEntity(
      verdict: verdict,
      colorHex: _colorHex(),
      headline: headline,
      headlineHi: headlineHi,
      plainEn: plainEn,
      plainHi: plainHi,
      safeWindow: parsedSafeWindow,
      variables: parsedVariables,
      hourlyChart: parsedHourly,
      sources: sources,
      sourcesFailed: sourcesFailed,
      knownSources: knownSources,
      totalSources: totalSources,
      timestamp: timestamp,
      staleness: staleness,
    );
  }
}
