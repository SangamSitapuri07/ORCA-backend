import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/orca_app_bar.dart';
import '../providers/agents_provider.dart';
import '../widgets/collaboration_trace_view.dart';

/// Runs and displays the real eleven-stage backend analysis trace.
class AiScreen extends ConsumerWidget {
  const AiScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final agentsState = ref.watch(agentsProvider);

    return Scaffold(
      appBar: OrcaAppBar(
        title: 'ORCA ANALYSIS',
        subtitle: '11 backend analysis stages',
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: OrcaTheme.accent),
            tooltip: 'Rerun backend analysis',
            onPressed: () {
              ref.read(agentsProvider.notifier).fetch(forceRefresh: true);
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(agentsProvider.notifier).fetch(forceRefresh: true);
        },
        color: OrcaTheme.accent,
        backgroundColor: OrcaTheme.surface,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(14),
          child: agentsState.when(
            data: (reasoning) => CollaborationTraceView(reasoning: reasoning),
            loading: () => const Center(
              child: Padding(
                padding: EdgeInsets.symmetric(vertical: 80),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    CircularProgressIndicator(color: OrcaTheme.accent),
                    SizedBox(height: 16),
                    Text(
                      'Running 11 ORCA analysis stages...',
                      style: TextStyle(color: OrcaTheme.textSecondary, fontSize: 14),
                    ),
                  ],
                ),
              ),
            ),
            error: (err, _) => Container(
              padding: const EdgeInsets.all(20),
              margin: const EdgeInsets.symmetric(vertical: 40),
              decoration: BoxDecoration(
                color: OrcaTheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: VerdictColors.critical),
              ),
              child: Column(
                children: [
                  const Icon(Icons.error_outline, color: VerdictColors.critical, size: 40),
                  const SizedBox(height: 10),
                  const Text(
                    'Backend Analysis Unavailable',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    err.toString(),
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 12, color: OrcaTheme.textSecondary),
                  ),
                  const SizedBox(height: 14),
                  ElevatedButton.icon(
                    onPressed: () {
                      ref.read(agentsProvider.notifier).fetch(forceRefresh: true);
                    },
                    icon: const Icon(Icons.refresh),
                    label: const Text('Rerun Analysis'),
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
