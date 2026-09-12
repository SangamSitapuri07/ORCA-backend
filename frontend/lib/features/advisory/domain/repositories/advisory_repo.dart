import '../../../../core/result/result.dart';
import '../entities/advisory.dart';

/// Contract for advisory data access (§10, §13).
abstract class AdvisoryRepository {
  /// Fetches advisory with cache-first and staleness tracking.
  Future<Result<AdvisoryEntity>> getAdvisory({
    required double lat,
    required double lon,
    bool forceRefresh = false,
  });
}
