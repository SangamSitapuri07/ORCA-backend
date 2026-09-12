import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';

/// Phase-2 catch persistence is intentionally unavailable until the real,
/// authenticated Supabase repository is supplied.
class CatchReportScreen extends StatelessWidget {
  const CatchReportScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('CATCH REPORT'), backgroundColor: OrcaTheme.surface),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.cloud_off, color: VerdictColors.caution, size: 52),
              SizedBox(height: 14),
              Text('Catch sync unavailable', style: TextStyle(fontSize: 19, fontWeight: FontWeight.bold, color: Colors.white)),
              SizedBox(height: 8),
              Text(
                'The team’s authenticated Supabase catch-report service has not been supplied. ORCA will not claim a report was uploaded or show seeded catches as real records.',
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
