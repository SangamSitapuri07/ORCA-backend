import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import '../../../../core/config/app_config.dart';
import '../../../../core/network/tile_url_provider.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/orca_app_bar.dart';
import '../../domain/entities/zone_snapshot.dart';
import '../providers/map_provider.dart';
import '../widgets/layer_selector_dialog.dart';
import '../widgets/probe_bottom_sheet.dart';

/// Interactive Ocean Map Screen with Tap Probe and Live Data Layers (§8).
class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final MapController _mapController = MapController();
  LatLng _currentLocation = const LatLng(AppConfig.defaultLat, AppConfig.defaultLon);
  LatLng? _probedLocation;

  @override
  Widget build(BuildContext context) {
    final probedSnapshotState = ref.watch(probedZoneProvider);
    final tileUrl = ref.watch(orcaTileUrlProvider);
    final layers = ref.watch(mapLayersProvider);
    final geoLayers = ref.watch(geoLayersProvider).valueOrNull;
    final enabled = layers.where((layer) => layer.isEnabled).map((layer) => layer.id).toSet();
    final features = (geoLayers?.features ?? const <GeoFeatureEntity>[]).where((feature) {
      final layer = feature.layer == 'cyclone_radius' ? 'cyclone' : feature.layer;
      return enabled.contains(layer);
    }).toList();
    final polylines = <Polyline>[];
    final polygons = <Polygon>[];
    final geoMarkers = <Marker>[];
    for (final feature in features) {
      final color = _layerColor(feature.layer);
      if (feature.point != null) {
        final point = feature.point!;
        geoMarkers.add(Marker(
          point: LatLng(point.lat, point.lon),
          width: 34,
          height: 34,
          child: Tooltip(
            message: feature.name,
            child: Icon(
              feature.layer == 'port' ? Icons.anchor : Icons.cyclone,
              color: color,
              size: 25,
            ),
          ),
        ));
      }
      for (final path in feature.paths) {
        final points = path.map((point) => LatLng(point.lat, point.lon)).toList();
        if (points.length < 2) continue;
        if (feature.geometryType.contains('Polygon')) {
          polygons.add(Polygon(
            points: points,
            color: color.withValues(alpha: 0.12),
            borderColor: color,
            borderStrokeWidth: 1.5,
          ));
        } else {
          polylines.add(Polyline(points: points, color: color, strokeWidth: 2.5));
        }
      }
    }

    return Scaffold(
      appBar: OrcaAppBar(
        title: 'OCEAN MAP & PROBE',
        subtitle: 'Tap ocean to probe live conditions',
        actions: [
          IconButton(
            icon: const Icon(Icons.layers_outlined, color: OrcaTheme.textPrimary),
            tooltip: 'Data Layers',
            onPressed: () {
              showDialog<void>(
                context: context,
                builder: (context) => const LayerSelectorDialog(),
              );
            },
          ),
        ],
      ),
      body: Stack(
        children: [
          // FlutterMap interactive view
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: _currentLocation,
              initialZoom: 9.0,
              minZoom: 4.0,
              maxZoom: 16.0,
              onTap: (tapPosition, point) {
                setState(() {
                  _probedLocation = point;
                });
                probeCoordinate(ref, point.latitude, point.longitude);
              },
            ),
            children: [
              // First-party ORCA Box tile proxy (not a nautical chart).
              if (tileUrl != null)
                TileLayer(
                  urlTemplate: tileUrl,
                  userAgentPackageName: 'com.orca.orca_app',
                ),
              if (polygons.isNotEmpty) PolygonLayer(polygons: polygons),
              if (polylines.isNotEmpty) PolylineLayer(polylines: polylines),

              // Markers layer (GIS features + vessel + probed pin)
              MarkerLayer(
                markers: [
                  ...geoMarkers,
                  // Vessel Position Marker
                  Marker(
                    point: _currentLocation,
                    width: 40,
                    height: 40,
                    child: Container(
                      decoration: BoxDecoration(
                        color: OrcaTheme.accent.withValues(alpha: 0.3),
                        shape: BoxShape.circle,
                      ),
                      child: const Center(
                        child: Icon(
                          Icons.navigation,
                          color: OrcaTheme.accent,
                          size: 24,
                        ),
                      ),
                    ),
                  ),

                  // Probed Spot Pin
                  if (_probedLocation != null)
                    Marker(
                      point: _probedLocation!,
                      width: 44,
                      height: 44,
                      child: const Icon(
                        Icons.location_on,
                        color: VerdictColors.noGo,
                        size: 38,
                      ),
                    ),
                ],
              ),
              const RichAttributionWidget(
                attributions: [TextSourceAttribution('© OpenStreetMap contributors · ODbL')],
              ),
            ],
          ),

          // Top Info Banner: Tap instruction
          Positioned(
            top: 10,
            left: 14,
            right: 14,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: OrcaTheme.surface.withValues(alpha: 0.9),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: OrcaTheme.cardBorder),
              ),
              child: const Row(
                children: [
                  Icon(Icons.touch_app, size: 16, color: OrcaTheme.accent),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Tap anywhere on the sea to probe waves, currents & SST.',
                      style: TextStyle(
                        fontSize: 11.5,
                        color: OrcaTheme.textPrimary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Floating GPS Locate Button
          Positioned(
            right: 16,
            bottom: probedSnapshotState != null ? 240 : 24,
            child: FloatingActionButton.small(
              heroTag: 'locate_btn',
              backgroundColor: OrcaTheme.surfaceElevated,
              foregroundColor: OrcaTheme.accent,
              onPressed: _locateVessel,
              child: const Icon(Icons.my_location),
            ),
          ),

          // Bottom Probe Sheet when spot is selected
          if (probedSnapshotState != null)
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: probedSnapshotState.when(
                data: (snapshot) => snapshot != null
                    ? ProbeBottomSheet(
                        snapshot: snapshot,
                        onClose: () {
                          setState(() {
                            _probedLocation = null;
                          });
                          ref.read(probedZoneProvider.notifier).state = null;
                        },
                      )
                    : const SizedBox.shrink(),
                loading: () => Container(
                  padding: const EdgeInsets.all(24),
                  decoration: const BoxDecoration(
                    color: OrcaTheme.surface,
                    borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
                  ),
                  child: const Center(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        CircularProgressIndicator(color: OrcaTheme.accent, strokeWidth: 2.5),
                        SizedBox(width: 14),
                        Text(
                          'Probing ocean spot conditions...',
                          style: TextStyle(color: Colors.white, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                ),
                error: (error, _) => Container(
                  padding: const EdgeInsets.all(16),
                  decoration: const BoxDecoration(
                    color: OrcaTheme.surface,
                    borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, color: VerdictColors.critical),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          error.toString(),
                          style: const TextStyle(color: Colors.white, fontSize: 12),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close, color: Colors.white70),
                        onPressed: () {
                          ref.read(probedZoneProvider.notifier).state = null;
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Color _layerColor(String layer) {
    switch (layer) {
      case 'official_pfz':
        return const Color(0xFF4ADE80);
      case 'cyclone':
      case 'cyclone_radius':
        return VerdictColors.noGo;
      case 'port':
        return OrcaTheme.accent;
      case 'eez':
        return const Color(0xFFA78BFA);
      default:
        return OrcaTheme.textMuted;
    }
  }

  Future<void> _locateVessel() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) return;
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) return;
    final position = await Geolocator.getCurrentPosition();
    final location = LatLng(position.latitude, position.longitude);
    if (!mounted) return;
    setState(() => _currentLocation = location);
    _mapController.move(location, 11.0);
  }
}
