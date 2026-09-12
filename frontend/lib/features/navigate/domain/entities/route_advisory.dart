// Re-export barrel: RouteAdvisoryEntity and TransitPoint live in route_check.dart.
// Files that import route_advisory.dart will correctly resolve via this barrel.
export 'route_check.dart' show RouteAdvisoryEntity, TransitPoint;
