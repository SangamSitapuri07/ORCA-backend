import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/network/dio_provider.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/orca_app_bar.dart';
import '../../../../core/widgets/toast.dart';
import '../providers/settings_provider.dart';
import '../widgets/server_config_dialog.dart';
import '../widgets/source_catalog_health_view.dart';

/// Info & System Settings Screen (§8, §10, §11).
class InfoScreen extends ConsumerWidget {
  const InfoScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(baseUrlProvider);
    final healthState = ref.watch(healthProvider);
    final cacheService = ref.watch(cacheServiceProvider);
    final selectedLocale = ref.watch(selectedLocaleProvider);

    return Scaffold(
      appBar: const OrcaAppBar(
        title: 'SYSTEM & DATA HEALTH',
        subtitle: 'ORCA Box Configuration & Sources',
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 1. Server URL Card
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: OrcaTheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: OrcaTheme.cardBorder),
              ),
              child: Row(
                children: [
                  const Icon(Icons.dns, color: OrcaTheme.accent, size: 24),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'ORCA BOX BASE URL',
                          style: TextStyle(
                            fontSize: 10.5,
                            fontWeight: FontWeight.w700,
                            color: OrcaTheme.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          baseUrl.isEmpty ? 'Not configured' : baseUrl,
                          style: const TextStyle(
                            fontSize: 13.5,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  OutlinedButton(
                    onPressed: () {
                      showDialog<void>(
                        context: context,
                        builder: (context) => const ServerConfigDialog(),
                      );
                    },
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(64, 36),
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                    ),
                    child: const Text('Change', style: TextStyle(fontSize: 12)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // Official Dashboard Access Card for Judges & Fisheries Officials
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: OrcaTheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.blue.withAlpha(120), width: 1.2),
              ),
              child: Row(
                children: [
                  const Icon(Icons.admin_panel_settings, color: Colors.blue, size: 24),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'OFFICIAL / FISHERIES DASHBOARD',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            color: Colors.blue,
                          ),
                        ),
                        SizedBox(height: 2),
                        Text(
                          'Phase 2 cloud aggregation status',
                          style: TextStyle(fontSize: 11, color: OrcaTheme.textMuted),
                        ),
                      ],
                    ),
                  ),
                  ElevatedButton(
                    onPressed: () {
                      context.push('/official-dashboard');
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blue,
                      foregroundColor: Colors.white,
                      minimumSize: const Size(64, 36),
                    ),
                    child: const Text('Status', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // 2. Language selector
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: OrcaTheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: OrcaTheme.cardBorder),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Language / भाषा / భాష',
                            style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.white),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'Select primary UI language',
                            style: TextStyle(fontSize: 11, color: OrcaTheme.textMuted),
                          ),
                        ],
                      ),
                      DropdownButton<String>(
                        value: selectedLocale,
                        dropdownColor: OrcaTheme.surfaceElevated,
                        underline: const SizedBox.shrink(),
                        items: const [
                          DropdownMenuItem(value: 'en', child: Text('English', style: TextStyle(color: Colors.white, fontSize: 13))),
                          DropdownMenuItem(value: 'hi', child: Text('हिन्दी (Hindi)', style: TextStyle(color: Colors.white, fontSize: 13))),
                          DropdownMenuItem(value: 'te', child: Text('తెలుగు (Telugu)', style: TextStyle(color: Colors.white, fontSize: 13))),
                        ],
                        onChanged: (val) async {
                          if (val != null) {
                            ref.read(selectedLocaleProvider.notifier).state = val;
                            await ref.read(cacheServiceProvider).put(
                              'settings.locale',
                              <String, dynamic>{'value': val},
                              ttl: const Duration(days: 3650),
                            );
                          }
                        },
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),

            // 3. Cache & Storage Management
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: OrcaTheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: OrcaTheme.cardBorder),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'LOCAL CACHE & STORAGE',
                        style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700, color: OrcaTheme.textSecondary),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${cacheService.keyCount} cached items active',
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.white),
                      ),
                    ],
                  ),
                  ElevatedButton.icon(
                    onPressed: () async {
                      await cacheService.clearAll();
                      if (!context.mounted) return;
                      ToastHelper.show(
                        context,
                        title: 'Cache Cleared',
                        message: 'Local Hive offline storage reset successfully.',
                        severity: 'info',
                      );
                    },
                    icon: const Icon(Icons.delete_outline, size: 16),
                    label: const Text('Clear', style: TextStyle(fontSize: 12)),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: OrcaTheme.surfaceElevated,
                      foregroundColor: Colors.white,
                      minimumSize: const Size(80, 36),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // 4. Source catalog configuration/capability report (§11)
            healthState.when(
              data: (snapshot) => SourceCatalogHealthView(liveSources: snapshot.dataSources),
              loading: () => const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: CircularProgressIndicator(color: OrcaTheme.accent),
                ),
              ),
              error: (err, _) => Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: OrcaTheme.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: VerdictColors.critical),
                ),
                child: Text(
                  'Health check error: $err',
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // 5. About ORCA Card
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: OrcaTheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: OrcaTheme.cardBorder),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'ABOUT ORCA (SIH26176 · ISRO)',
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: OrcaTheme.textSecondary, letterSpacing: 0.8),
                  ),
                  SizedBox(height: 6),
                  Text(
                    'Marine EcOsystem Reasoning with Collaborative Agents.\nDesigned for low-literacy fishers, high sunlight readability, and honest data provenance.',
                    style: TextStyle(fontSize: 12, color: OrcaTheme.textPrimary, height: 1.35),
                  ),
                  SizedBox(height: 8),
                  Text(
                    'Client Version 1.0.0 · Edge Box Architecture',
                    style: TextStyle(fontSize: 10.5, color: OrcaTheme.textMuted),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
