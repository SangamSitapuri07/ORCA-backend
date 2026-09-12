import 'alert_item.dart';

/// Active alerts plus evidence from the backend's latest location check.
class AlertsSnapshot {
  final List<AlertItem> alerts;
  final List<String> sourcesUsed;
  final List<String> sourcesFailed;
  final DateTime? checkedAt;

  const AlertsSnapshot({
    required this.alerts,
    this.sourcesUsed = const <String>[],
    this.sourcesFailed = const <String>[],
    this.checkedAt,
  });

  bool get hasEvaluationEvidence =>
      checkedAt != null && (sourcesUsed.isNotEmpty || sourcesFailed.isNotEmpty);

  bool get checkIncomplete => !hasEvaluationEvidence || sourcesFailed.isNotEmpty;

  AlertsSnapshot withAlerts(List<AlertItem> nextAlerts) {
    return AlertsSnapshot(
      alerts: nextAlerts,
      sourcesUsed: sourcesUsed,
      sourcesFailed: sourcesFailed,
      checkedAt: checkedAt,
    );
  }
}
