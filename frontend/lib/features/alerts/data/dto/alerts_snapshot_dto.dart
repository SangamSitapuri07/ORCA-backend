import '../../domain/entities/alerts_snapshot.dart';
import 'alert_dto.dart';

class AlertsSnapshotDto {
  final List<AlertDto> alerts;
  final List<String> sourcesUsed;
  final List<String> sourcesFailed;
  final DateTime? checkedAt;

  const AlertsSnapshotDto({
    required this.alerts,
    required this.sourcesUsed,
    required this.sourcesFailed,
    required this.checkedAt,
  });

  factory AlertsSnapshotDto.fromJson(Map<String, dynamic> json) {
    final rawAlerts = json['alerts'];
    final evaluation = json['evaluation'] is Map
        ? Map<String, dynamic>.from(json['evaluation'] as Map)
        : const <String, dynamic>{};

    List<String> strings(dynamic value) {
      return value is List
          ? value.whereType<Object>().map((item) => item.toString()).toList()
          : <String>[];
    }

    return AlertsSnapshotDto(
      alerts: rawAlerts is List
          ? rawAlerts
                .whereType<Map>()
                .map((item) => AlertDto.fromJson(Map<String, dynamic>.from(item)))
                .toList()
          : <AlertDto>[],
      sourcesUsed: strings(evaluation['sources_used']),
      sourcesFailed: strings(evaluation['sources_failed']),
      checkedAt: DateTime.tryParse(evaluation['checked_at'] as String? ?? ''),
    );
  }

  AlertsSnapshot toEntity() {
    return AlertsSnapshot(
      alerts: alerts.map((dto) => dto.toEntity()).toList(),
      sourcesUsed: sourcesUsed,
      sourcesFailed: sourcesFailed,
      checkedAt: checkedAt,
    );
  }
}
