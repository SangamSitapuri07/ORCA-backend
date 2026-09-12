import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/orca_app_bar.dart';
import '../../../../core/widgets/toast.dart';
import '../../../settings/presentation/providers/settings_provider.dart';
import '../providers/alerts_provider.dart';
import '../widgets/alert_card.dart';

/// Alerts feed with SSE updates and a backend-controlled drill action (§8, §19).
class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alertsState = ref.watch(alertsProvider);
    final health = ref.watch(healthProvider).valueOrNull;
    final demoAlerts = health?.components['demo_alerts'];
    final drillEnabled = demoAlerts is Map && demoAlerts['status'] == 'enabled';

    return Scaffold(
      appBar: OrcaAppBar(
        title: 'MARINE ALERTS',
        subtitle: 'Active Cyclone & Weather Warnings',
        actions: [
          if (drillEnabled)
            IconButton(
              icon: const Icon(Icons.notification_add_outlined, color: VerdictColors.caution),
              tooltip: 'Request labelled drill alert from ORCA Box',
              onPressed: () async {
                final created = await ref.read(alertsProvider.notifier).simulateDemoAlert();
                if (!context.mounted) return;
                ToastHelper.show(
                  context,
                  title: created ? 'Drill Alert Created' : 'Drill Alert Failed',
                  message: created
                      ? 'The ORCA Box created a clearly labelled simulated alert.'
                      : 'The ORCA Box rejected or could not create the drill alert.',
                  severity: created ? 'caution' : 'critical',
                );
              },
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(alertsProvider.notifier).fetch(forceRefresh: true);
        },
        color: OrcaTheme.accent,
        backgroundColor: OrcaTheme.surface,
        child: alertsState.when(
          data: (alerts) {
            if (alerts.isEmpty) {
              return SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 80),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: VerdictColors.caution.withValues(alpha: 0.1),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.help_outline, color: VerdictColors.caution, size: 56),
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'No Alerts Available',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'This is not an all-clear. Refresh to ask the ORCA Box to check live weather and cyclone sources.',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 13, color: OrcaTheme.textSecondary),
                      ),
                    ],
                  ),
                ),
              );
            }

            return ListView.builder(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              itemCount: alerts.length,
              itemBuilder: (context, index) {
                return AlertCard(alert: alerts[index]);
              },
            );
          },
          loading: () => const Center(
            child: CircularProgressIndicator(color: OrcaTheme.accent),
          ),
          error: (err, _) => Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, color: VerdictColors.critical, size: 40),
                  const SizedBox(height: 12),
                  Text(
                    'Failed to load alerts: $err',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                  ),
                  const SizedBox(height: 12),
                  ElevatedButton(
                    onPressed: () {
                      ref.read(alertsProvider.notifier).fetch(forceRefresh: true);
                    },
                    child: const Text('Retry'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
