import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/orca_app_bar.dart';
import '../../../../core/widgets/source_footer.dart';
import '../providers/navigate_provider.dart';
import '../widgets/route_verdict_card.dart';
import '../widgets/transit_points_strip.dart';

/// Predefined harbour destinations for quick skipper selection.
final harboursList = <Map<String, dynamic>>[
  {'name': 'Sasoon Docks, Mumbai', 'lat': 18.92, 'lon': 72.83},
  {'name': 'Alibaug Fish Landing', 'lat': 18.65, 'lon': 72.88},
  {'name': 'PFZ Hotspot Delta-4', 'lat': 18.75, 'lon': 72.55},
  {'name': 'Ratnagiri Port', 'lat': 16.98, 'lon': 73.28},
  {'name': 'Veraval Harbour, Gujarat', 'lat': 20.90, 'lon': 70.37},
];

/// Navigate & Route Transit Safety Screen (§8, §21).
class NavigateScreen extends ConsumerStatefulWidget {
  const NavigateScreen({super.key});

  @override
  ConsumerState<NavigateScreen> createState() => _NavigateScreenState();
}

class _NavigateScreenState extends ConsumerState<NavigateScreen> {
  int _fromIndex = 0; // Sasoon Docks
  int _toIndex = 2; // PFZ Hotspot Delta-4

  @override
  Widget build(BuildContext context) {
    final routeState = ref.watch(navigateProvider);

    final fromPort = harboursList[_fromIndex];
    final toPort = harboursList[_toIndex];

    return Scaffold(
      appBar: const OrcaAppBar(
        title: 'ROUTE NAVIGATION',
        subtitle: 'Land Collision Check & Transit Verdict',
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Route Selector Card
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: OrcaTheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: OrcaTheme.cardBorder),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // From Departure
                  const Text(
                    'DEPARTURE HARBOUR',
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w700,
                      color: OrcaTheme.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  DropdownButtonFormField<int>(
                    // ignore: deprecated_member_use
                    value: _fromIndex,
                    dropdownColor: OrcaTheme.surfaceElevated,
                    decoration: InputDecoration(
                      prefixIcon: const Icon(Icons.anchor, color: OrcaTheme.accent, size: 20),
                      filled: true,
                      fillColor: OrcaTheme.surfaceElevated,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide.none,
                      ),
                    ),
                    items: List.generate(
                      harboursList.length,
                      (i) => DropdownMenuItem(
                        value: i,
                        child: Text(
                          harboursList[i]['name'] as String,
                          style: const TextStyle(fontSize: 13, color: Colors.white),
                        ),
                      ),
                    ),
                    onChanged: (val) {
                      if (val != null) setState(() => _fromIndex = val);
                    },
                  ),
                  const SizedBox(height: 12),

                  // To Destination
                  const Text(
                    'DESTINATION SPOT / PFZ',
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w700,
                      color: OrcaTheme.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  DropdownButtonFormField<int>(
                    // ignore: deprecated_member_use
                    value: _toIndex,
                    dropdownColor: OrcaTheme.surfaceElevated,
                    decoration: InputDecoration(
                      prefixIcon: const Icon(Icons.location_on, color: VerdictColors.caution, size: 20),
                      filled: true,
                      fillColor: OrcaTheme.surfaceElevated,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide.none,
                      ),
                    ),
                    items: List.generate(
                      harboursList.length,
                      (i) => DropdownMenuItem(
                        value: i,
                        child: Text(
                          harboursList[i]['name'] as String,
                          style: const TextStyle(fontSize: 13, color: Colors.white),
                        ),
                      ),
                    ),
                    onChanged: (val) {
                      if (val != null) setState(() => _toIndex = val);
                    },
                  ),
                  const SizedBox(height: 14),

                  // Evaluate Button
                  ElevatedButton.icon(
                    onPressed: () {
                      ref.read(navigateProvider.notifier).evaluateRoute(
                            fromLat: fromPort['lat'] as double,
                            fromLon: fromPort['lon'] as double,
                            toLat: toPort['lat'] as double,
                            toLon: toPort['lon'] as double,
                          );
                    },
                    icon: const Icon(Icons.directions_boat),
                    label: const Text('Verify Route Safety & Land Clearance'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),

            // Route evaluation state
            routeState.when(
              data: (state) {
                if (state.advisory == null) {
                  return const SizedBox.shrink();
                }

                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    RouteVerdictCard(
                      advisory: state.advisory!,
                      check: state.check,
                    ),
                    const SizedBox(height: 14),
                    TransitPointsStrip(points: state.advisory!.points),
                    const SizedBox(height: 14),
                    SourceFooter(sources: state.advisory!.sources),
                  ],
                );
              },
              loading: () => const Center(
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Column(
                    children: [
                      CircularProgressIndicator(color: OrcaTheme.accent),
                      SizedBox(height: 12),
                      Text(
                        'Sampling route every 30km & testing GLOBE land mask...',
                        style: TextStyle(color: OrcaTheme.textSecondary, fontSize: 13),
                      ),
                    ],
                  ),
                ),
              ),
              error: (err, _) => Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: OrcaTheme.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: VerdictColors.critical),
                ),
                child: Text(
                  'Route verification failed: $err',
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
