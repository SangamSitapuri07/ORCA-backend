import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';

/// Phase-2 official aggregation requires the team's authoritative Supabase
/// implementation. Showing an explicit unavailable state prevents fabricated
/// fleet counts, sector verdicts, or catch totals from entering production.
class OfficialDashboardScreen extends StatelessWidget {
  const OfficialDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('OFFICIAL DASHBOARD'),
        backgroundColor: OrcaTheme.surface,
      ),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.cloud_off, color: VerdictColors.caution, size: 56),
              SizedBox(height: 16),
              Text(
                'Cloud dashboard unavailable',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white),
              ),
              SizedBox(height: 10),
              Text(
                'The authoritative Supabase aggregation and authorization implementation has not been supplied. No fleet, catch, or sector totals are being invented. Core ORCA Box safety advisories remain available.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, color: OrcaTheme.textSecondary, height: 1.45),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
