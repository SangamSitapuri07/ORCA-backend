import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/widgets/orca_app_bar.dart';
import '../providers/agents_provider.dart';
import '../widgets/chat_tab_view.dart';
import '../widgets/collaboration_trace_view.dart';

/// AI Multi-Agent Screen showcasing 10-Agent collaboration & trace (§3, §8).
class AiScreen extends ConsumerStatefulWidget {
  const AiScreen({super.key});

  @override
  ConsumerState<AiScreen> createState() => _AiScreenState();
}

class _AiScreenState extends ConsumerState<AiScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final agentsState = ref.watch(agentsProvider);

    return Scaffold(
      appBar: OrcaAppBar(
        title: 'ORCA AI AGENTS',
        subtitle: '10-Agent Multi-Model Collaboration Board',
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh, color: OrcaTheme.accent),
            tooltip: 'Rerun 10-Agent Pipeline',
            onPressed: () {
              ref.read(agentsProvider.notifier).fetch(forceRefresh: true);
            },
          ),
        ],
      ),
      body: Column(
        children: [
          // Tab bar: Live Trace vs Assistant Q&A
          Container(
            color: OrcaTheme.surface,
            child: TabBar(
              controller: _tabController,
              indicatorColor: OrcaTheme.accent,
              indicatorWeight: 3.0,
              labelColor: OrcaTheme.accent,
              unselectedLabelColor: OrcaTheme.textSecondary,
              labelStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
              tabs: const [
                Tab(
                  icon: Icon(Icons.hub_outlined, size: 18),
                  text: 'Collaboration Trace',
                ),
                Tab(
                  icon: Icon(Icons.chat_bubble_outline, size: 18),
                  text: 'LLM Assistant',
                ),
              ],
            ),
          ),

          // Tab View Content
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: [
                // Tab 1: Collaboration Trace
                RefreshIndicator(
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
                              'Agent Reasoning Unavailable',
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
                              label: const Text('Rerun Agents'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),

                // Tab 2: LLM Assistant
                const ChatTabView(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
