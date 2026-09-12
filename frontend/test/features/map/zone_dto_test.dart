import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/cache/staleness.dart';
import 'package:orca_app/features/map/data/dto/zone_dto.dart';

void main() {
  test('preserves per-observation source and time metadata', () {
    final dto = ZoneDto.fromJson({
      'lat': 19.0,
      'lon': 72.8,
      'sst_mean': 28.4,
      'chlorophyll': 0.42,
      'fetched_at': '2026-09-12T09:00:00Z',
      'data_sources_used': ['Open-Meteo Marine', 'ESA OC-CCI'],
      'observation_metadata': {
        'sea_temp_c': {
          'source': 'Open-Meteo Marine API',
          'observed_from': '2026-08-08',
          'observed_to': '2026-09-08',
          'statistic': 'Mean of available daily maximum SST values in this period',
        },
        'chlorophyll_mg_m3': {
          'source': 'ESA OC-CCI v6',
          'observed_at': '2026-09-09',
          'note': 'Cached result read 25 min ago',
        },
      },
    });

    final entity = dto.toEntity(
      StalenessInfo.fromDateTime(dto.sourceTimestamp),
    );

    expect(entity.observations['sea_temp_c']?.source, 'Open-Meteo Marine API');
    expect(
      entity.observations['sea_temp_c']?.timeLabel,
      '2026-08-08 to 2026-09-08',
    );
    expect(entity.observations['chlorophyll_mg_m3']?.timeLabel, '2026-09-09');
    expect(
      entity.observations['chlorophyll_mg_m3']?.note,
      'Cached result read 25 min ago',
    );
  });
}
