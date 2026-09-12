import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';

/// Chat tab view demonstrating honest unavailable / paused status (§4, §8).
class ChatTabView extends StatelessWidget {
  const ChatTabView({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Honest Status Card
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: OrcaTheme.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: VerdictColors.info, width: 1.2),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.pause_circle_outline, color: VerdictColors.info, size: 22),
                    SizedBox(width: 8),
                    Text(
                      'Ollama LLM Chat: Paused by Design',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
                SizedBox(height: 8),
                Text(
                  'To preserve edge computational resources and battery on the ORCA Box laptop, unstructured conversational chat is currently paused. The 11 deterministic and optionally Ollama-enriched stages run in the Trace tab above.',
                  style: TextStyle(
                    fontSize: 12.5,
                    color: OrcaTheme.textSecondary,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          const Text(
            'DEMONSTRATION SAMPLE QUERIES',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              color: OrcaTheme.textSecondary,
              letterSpacing: 0.8,
            ),
          ),
          const SizedBox(height: 8),

          _sampleQueryCard(
            '🌊 "Why is wave steepness dangerous after 16:00?"',
            'Ocean Analysis Agent: Swell period decreases to 7.8s while height reaches 2.9m, creating short-period steep chop with steepness index > 0.045.',
          ),
          _sampleQueryCard(
            '🎣 "Where are today\'s INCOIS Potential Fishing Zones?"',
            'Fisheries Agent: Line #MH-26-09 is located 3.8 km NW of Sasoon Docks at depth 42m with active chlorophyll fronts (0.82 mg/m³).',
          ),
          _sampleQueryCard(
            '🚨 "Why is the overall verdict Caution and not Go?"',
            'Marine Risk Agent: Worst-case fold logic flagged significant wave height (2.6m) crossing the 2.5m small-craft threshold despite favorable wind and clear land clearance.',
          ),
        ],
      ),
    );
  }

  Widget _sampleQueryCard(String question, String answer) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.symmetric(vertical: 5),
      decoration: BoxDecoration(
        color: OrcaTheme.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: OrcaTheme.cardBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            question,
            style: const TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: OrcaTheme.accent,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            answer,
            style: const TextStyle(
              fontSize: 11.5,
              color: OrcaTheme.textPrimary,
              height: 1.3,
            ),
          ),
        ],
      ),
    );
  }
}
