import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/offline/connectivity_watcher.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../../../core/widgets/orca_app_bar.dart';
import '../../../../core/widgets/source_footer.dart';
import '../providers/advisory_provider.dart';
import '../widgets/hourly_chart.dart';
import '../widgets/safe_window_bar.dart';
import '../widgets/variables_grid.dart';
import '../widgets/verdict_card.dart';

/// Primary Fisher Safety Home Screen (§8, §26A, Phase 2).
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final advisoryState = ref.watch(advisoryProvider);
    final isOnline = ref.watch(isOnlineProvider);

    return Scaffold(
      appBar: const OrcaAppBar(
        title: 'ORCA ADVISORY',
        subtitle: 'Marine Safety & Weather Intelligence',
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(advisoryProvider.notifier).fetch(forceRefresh: true);
        },
        color: OrcaTheme.accent,
        backgroundColor: OrcaTheme.surface,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Offline notice banner if disconnected (§14)
              if (!isOnline) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: BoxDecoration(
                    color: VerdictColors.cautionBg,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: VerdictColors.caution, width: 1.0),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.wifi_off, color: VerdictColors.caution, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: const Text(
                          'You are offline. Showing the last cached advisory with its original observation time.',
                          style: const TextStyle(
                            fontSize: 12,
                            color: Colors.white,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              // Main advisory state handling
              advisoryState.when(
                data: (advisory) => Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    VerdictCard(advisory: advisory),
                    const SizedBox(height: 12),
                    SafeWindowBar(safeWindow: advisory.safeWindow),
                    const SizedBox(height: 14),
                    VariablesGrid(variables: advisory.variables),
                    const SizedBox(height: 14),
                    HourlyChart(hourlyPoints: advisory.hourlyChart),
                    const SizedBox(height: 14),
                    SourceFooter(
                      sources: advisory.sources,
                      timeLabel: DateFormatter.formatIstTime(advisory.timestamp),
                    ),
                  ],
                ),
                loading: () => const Center(
                  child: Padding(
                    padding: EdgeInsets.symmetric(vertical: 80),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        CircularProgressIndicator(color: OrcaTheme.accent),
                        SizedBox(height: 16),
                        Text(
                          'Fetching live ocean observations...',
                          style: TextStyle(
                            color: OrcaTheme.textSecondary,
                            fontSize: 14,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                error: (error, _) => Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  margin: const EdgeInsets.symmetric(vertical: 40),
                  decoration: BoxDecoration(
                    color: OrcaTheme.surface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: VerdictColors.critical, width: 1.5),
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline, color: VerdictColors.critical, size: 48),
                      const SizedBox(height: 12),
                      const Text(
                        'Unable to Load Advisory',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        error.toString(),
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontSize: 13,
                          color: OrcaTheme.textSecondary,
                        ),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton.icon(
                        onPressed: () {
                          ref.read(advisoryProvider.notifier).fetch(forceRefresh: true);
                        },
                        icon: const Icon(Icons.refresh),
                        label: const Text('Retry Connection'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: OrcaTheme.accent,
                          foregroundColor: Colors.black,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
