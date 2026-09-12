import 'package:flutter_test/flutter_test.dart';
import 'package:orca_app/core/network/source_catalog.dart';

void main() {
  group('SourceCatalog Tests', () {
    test('Contains every backend-reported Phase-1 source', () {
      expect(SourceCatalog.all.length, equals(17));
    });

    test('Source key lookup works for MOSDAC, NOAA, and GLOBE', () {
      final mosdac = SourceCatalog.findByKey('isro_mosdac');
      expect(mosdac, isNotNull);
      expect(mosdac!.agency, contains('ISRO'));

      final noaa = SourceCatalog.findByKey('noaa_coastwatch');
      expect(noaa, isNotNull);
      expect(noaa!.host, equals('coastwatch.noaa.gov'));

      final globe = SourceCatalog.findByKey('globe_landmask');
      expect(globe, isNotNull);
      expect(globe!.authType, contains('Offline'));
    });
  });
}
