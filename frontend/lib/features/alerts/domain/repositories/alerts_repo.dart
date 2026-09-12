import '../../../../core/result/result.dart';
import '../entities/alert_item.dart';

abstract class AlertsRepository {
  Future<Result<List<AlertItem>>> getActiveAlerts({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  });

  Future<Result<AlertItem>> simulateAlert({
    required double lat,
    required double lon,
  });
}
