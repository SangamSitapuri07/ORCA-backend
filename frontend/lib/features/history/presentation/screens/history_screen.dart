import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';

/// Advisory history is a Phase-2 cloud-memory feature. Until the real
/// persistence source is supplied, this screen must not display sample events
/// as if they were a fisher's history.
class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('ADVISORY HISTORY'), backgroundColor: OrcaTheme.surface),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.history_toggle_off, color: VerdictColors.caution, size: 52),
              SizedBox(height: 14),
              Text('Cloud history unavailable', style: TextStyle(fontSize: 19, fontWeight: FontWeight.bold, color: Colors.white)),
              SizedBox(height: 8),
              Text(
                'No durable Supabase history implementation is connected. Core advisory requests and on-device cache fallback remain independent of cloud history.',
                textAlign: TextAlign.center,
                style: TextStyle(color: OrcaTheme.textSecondary, height: 1.4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
