import '../../../../core/result/result.dart';
import '../entities/alert_item.dart';
import '../entities/alerts_snapshot.dart';

abstract class AlertsRepository {
  Future<Result<AlertsSnapshot>> getActiveAlerts({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  });

  Future<Result<AlertItem>> simulateAlert({
    required double lat,
    required double lon,
  });
}
