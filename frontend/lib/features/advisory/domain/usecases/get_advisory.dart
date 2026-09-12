import '../../../../core/result/result.dart';
import '../entities/advisory.dart';
import '../repositories/advisory_repo.dart';

/// Usecase retrieving current advisory (§10).
class GetAdvisoryUseCase {
  final AdvisoryRepository _repository;

  GetAdvisoryUseCase(this._repository);

  Future<Result<AdvisoryEntity>> execute({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  }) {
    return _repository.getAdvisory(
      lat: lat,
      lon: lon,
      forceRefresh: forceRefresh,
    );
  }
}
