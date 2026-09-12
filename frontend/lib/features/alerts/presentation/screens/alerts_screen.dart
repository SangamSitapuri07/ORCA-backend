import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/orca_app_bar.dart';
import '../../../../core/widgets/toast.dart';
import '../../../settings/presentation/providers/settings_provider.dart';
import '../../domain/entities/alerts_snapshot.dart';
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
          data: (snapshot) {
            final alerts = snapshot.alerts;
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
                      Text(
                        snapshot.checkIncomplete
                            ? 'Alert Check Incomplete'
                            : 'No Active Alerts Reported',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        snapshot.checkIncomplete
                            ? snapshot.sourcesFailed.isNotEmpty
                                ? 'Some providers could not be checked. This is not an all-clear.'
                                : 'The backend did not return complete source/time evidence. This is not an all-clear.'
                            : 'No alert was returned by the checked sources. Continue checking official bulletins.',
                        textAlign: TextAlign.center,
                        style: const TextStyle(fontSize: 13, color: OrcaTheme.textSecondary),
                      ),
                      if (snapshot.checkedAt != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Checked ${_checkedAtLabel(snapshot.checkedAt!)}',
                          style: const TextStyle(fontSize: 11, color: OrcaTheme.textMuted),
                        ),
                      ],
                      if (snapshot.checkIncomplete) ...[
                        const SizedBox(height: 16),
                        _AlertEvidencePanel(snapshot: snapshot),
                      ],
                    ],
                  ),
                ),
              );
            }

            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              children: [
                if (snapshot.checkIncomplete) ...[
                  _AlertEvidencePanel(snapshot: snapshot),
                  const SizedBox(height: 10),
                ],
                ...alerts.map((alert) => AlertCard(alert: alert)),
              ],
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

String _checkedAtLabel(DateTime value) {
  final local = value.toLocal();
  String two(int number) => number.toString().padLeft(2, '0');
  return '${two(local.hour)}:${two(local.minute)} · '
      '${two(local.day)}/${two(local.month)}/${local.year}';
}

class _AlertEvidencePanel extends StatelessWidget {
  final AlertsSnapshot snapshot;

  const _AlertEvidencePanel({required this.snapshot});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: VerdictColors.caution.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: VerdictColors.caution.withValues(alpha: 0.35)),
      ),
      child: ExpansionTile(
        leading: const Icon(Icons.warning_amber_rounded, color: VerdictColors.caution),
        iconColor: VerdictColors.caution,
        collapsedIconColor: OrcaTheme.textSecondary,
        title: Text(
          snapshot.sourcesFailed.isEmpty
              ? 'Alert-check evidence incomplete'
              : '${snapshot.sourcesFailed.length} provider check(s) unavailable',
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.w700,
          ),
        ),
        subtitle: Text(
          snapshot.checkedAt == null
              ? 'Tap for technical details'
              : 'Checked ${_checkedAtLabel(snapshot.checkedAt!)} · tap for details',
          style: const TextStyle(color: OrcaTheme.textMuted, fontSize: 11),
        ),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
        children: [
          if (snapshot.sourcesUsed.isEmpty && snapshot.sourcesFailed.isEmpty)
            const Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'No per-source evaluation evidence was returned.',
                style: TextStyle(color: OrcaTheme.textSecondary, fontSize: 11),
              ),
            ),
          if (snapshot.checkedAt == null)
            const Align(
              alignment: Alignment.centerLeft,
              child: Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text(
                  'Evaluation time was not returned.',
                  style: TextStyle(color: OrcaTheme.textSecondary, fontSize: 11),
                ),
              ),
            ),
          for (final failure in snapshot.sourcesFailed)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('• ', style: TextStyle(color: VerdictColors.caution)),
                  Expanded(
                    child: Text(
                      failure,
                      style: const TextStyle(color: OrcaTheme.textSecondary, fontSize: 11),
                    ),
                  ),
                ],
              ),
            ),
          if (snapshot.sourcesUsed.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              'Checked successfully: ${snapshot.sourcesUsed.join(", ")}',
              style: const TextStyle(color: OrcaTheme.textMuted, fontSize: 11),
            ),
          ],
        ],
      ),
    );
  }
}
