import '../../../../core/utils/date_formatter.dart';
import '../../domain/entities/zone_snapshot.dart';

class GeoLayersDto {
  final Map<String, dynamic> json;

  const GeoLayersDto(this.json);

  static List<String> _strings(dynamic value) => value is List
      ? value.map((item) => item.toString()).toList()
      : <String>[];

  static GeoCoordinate? _coordinate(dynamic raw) {
    if (raw is! List || raw.length < 2 || raw[0] is! num || raw[1] is! num) {
      return null;
    }
    return GeoCoordinate((raw[1] as num).toDouble(), (raw[0] as num).toDouble());
  }

  static List<GeoCoordinate> _line(dynamic raw) {
    if (raw is! List) return const <GeoCoordinate>[];
    return raw.map(_coordinate).whereType<GeoCoordinate>().toList();
  }

  static List<List<GeoCoordinate>> _paths(String type, dynamic coordinates) {
    if (coordinates is! List) return const <List<GeoCoordinate>>[];
    switch (type) {
      case 'LineString':
        return <List<GeoCoordinate>>[_line(coordinates)];
      case 'MultiLineString':
      case 'Polygon':
        return coordinates.map(_line).where((line) => line.isNotEmpty).toList();
      case 'MultiPolygon':
        final paths = <List<GeoCoordinate>>[];
        for (final polygon in coordinates) {
          if (polygon is List) {
            paths.addAll(polygon.map(_line).where((line) => line.isNotEmpty));
          }
        }
        return paths;
      default:
        return const <List<GeoCoordinate>>[];
    }
  }

  GeoLayerCollection toEntity() {
    final parsed = <GeoFeatureEntity>[];
    final rawFeatures = json['features'] is List ? json['features'] as List : const [];
    for (final raw in rawFeatures) {
      if (raw is! Map) continue;
      final feature = Map<String, dynamic>.from(raw);
      if (feature['geometry'] is! Map) continue;
      final geometry = Map<String, dynamic>.from(feature['geometry'] as Map);
      final properties = feature['properties'] is Map
          ? Map<String, dynamic>.from(feature['properties'] as Map)
          : <String, dynamic>{};
      final type = geometry['type'] as String? ?? '';
      final point = type == 'Point' ? _coordinate(geometry['coordinates']) : null;
      final paths = _paths(type, geometry['coordinates']);
      if (point == null && paths.isEmpty) continue;
      parsed.add(GeoFeatureEntity(
        layer: properties['layer'] as String? ?? 'unknown',
        name: properties['name'] as String? ?? 'Unnamed feature',
        geometryType: type,
        point: point,
        paths: paths,
        properties: properties,
      ));
    }

    return GeoLayerCollection(
      features: parsed,
      sources: _strings(json['sources']),
      errors: _strings(json['errors']),
      generatedAt: DateFormatter.parseIso(json['generated_at'] as String?) ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    );
  }
}
