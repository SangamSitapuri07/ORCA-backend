import '../../../../core/result/result.dart';
import '../entities/alert_item.dart';
import '../repositories/alerts_repo.dart';

class GetAlertsUseCase {
  final AlertsRepository _repository;

  GetAlertsUseCase(this._repository);

  Future<Result<List<AlertItem>>> execute({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  }) {
    return _repository.getActiveAlerts(
      lat: lat,
      lon: lon,
      forceRefresh: forceRefresh,
    );
  }

  Future<Result<AlertItem>> simulate({
    required double lat,
    required double lon,
  }) {
    return _repository.simulateAlert(lat: lat, lon: lon);
  }
}
