import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../providers/auth_provider.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(userProfileProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'FISHER PROFILE',
          style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.2),
        ),
        backgroundColor: OrcaTheme.surface,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Profile Card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: OrcaTheme.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: OrcaTheme.accent.withAlpha(100)),
              ),
              child: Row(
                children: [
                  const CircleAvatar(
                    radius: 30,
                    backgroundColor: OrcaTheme.accent,
                    child: Icon(Icons.person, color: Colors.black, size: 36),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          profile.displayName,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${profile.vesselType} • ${profile.homeHarbour}',
                          style: const TextStyle(color: OrcaTheme.textSecondary, fontSize: 12),
                        ),
                        const SizedBox(height: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: VerdictColors.cautionBg,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'LOCAL PROFILE • CLOUD SYNC UNAVAILABLE',
                            style: TextStyle(color: VerdictColors.caution, fontSize: 10, fontWeight: FontWeight.bold),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),

            const Text(
              'Personal & Vessel Settings',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
            ),
            const SizedBox(height: 10),

            _buildTile(
              icon: Icons.language,
              title: 'Preferred Language',
              subtitle: profile.preferredLanguage.toUpperCase(),
              onTap: () {
                _showLanguagePicker(context, ref, profile.preferredLanguage);
              },
            ),
            _buildTile(
              icon: Icons.anchor,
              title: 'Home Harbour',
              subtitle: profile.homeHarbour,
              onTap: () {},
            ),
            _buildTile(
              icon: Icons.directions_boat,
              title: 'Vessel Type & Reg',
              subtitle: profile.vesselRegistration == null
                  ? profile.vesselType
                  : '${profile.vesselType} (${profile.vesselRegistration})',
              onTap: () {},
            ),
            _buildTile(
              icon: Icons.place,
              title: 'Primary Fishing Zone',
              subtitle: profile.preferredFishingArea,
              onTap: () {},
            ),

            const SizedBox(height: 20),
            const Text(
              'Notification Preferences',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
            ),
            const SizedBox(height: 10),

            SwitchListTile(
              value: profile.notificationPreferences['wave_alerts'] ?? true,
              onChanged: (val) => ref.read(userProfileProvider.notifier).toggleNotification('wave_alerts', val),
              title: const Text('High Wave & Swell Warnings', style: TextStyle(color: Colors.white)),
              tileColor: OrcaTheme.surface,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              activeColor: OrcaTheme.accent,
            ),
            const SizedBox(height: 8),
            SwitchListTile(
              value: profile.notificationPreferences['cyclone_alerts'] ?? true,
              onChanged: (val) => ref.read(userProfileProvider.notifier).toggleNotification('cyclone_alerts', val),
              title: const Text('Cyclone & Storm Alerts', style: TextStyle(color: Colors.white)),
              tileColor: OrcaTheme.surface,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              activeColor: OrcaTheme.accent,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTile({required IconData icon, required String title, required String subtitle, required VoidCallback onTap}) {
    return Card(
      color: OrcaTheme.surface,
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(icon, color: OrcaTheme.accent),
        title: Text(title, style: const TextStyle(color: Colors.white, fontSize: 14)),
        subtitle: Text(subtitle, style: const TextStyle(color: OrcaTheme.textSecondary, fontSize: 12)),
        trailing: const Icon(Icons.chevron_right, color: Colors.grey),
        onTap: onTap,
      ),
    );
  }

  void _showLanguagePicker(BuildContext context, WidgetRef ref, String currentLang) {
    showModalBottomSheet(
      context: context,
      backgroundColor: OrcaTheme.surface,
      builder: (ctx) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            title: const Text('English', style: TextStyle(color: Colors.white)),
            trailing: currentLang == 'en' ? const Icon(Icons.check, color: OrcaTheme.accent) : null,
            onTap: () {
              ref.read(userProfileProvider.notifier).updateLanguage('en');
              Navigator.pop(ctx);
            },
          ),
          ListTile(
            title: const Text('हिंदी (Hindi)', style: TextStyle(color: Colors.white)),
            trailing: currentLang == 'hi' ? const Icon(Icons.check, color: OrcaTheme.accent) : null,
            onTap: () {
              ref.read(userProfileProvider.notifier).updateLanguage('hi');
              Navigator.pop(ctx);
            },
          ),
          ListTile(
            title: const Text('తెలుగు (Telugu)', style: TextStyle(color: Colors.white)),
            trailing: currentLang == 'te' ? const Icon(Icons.check, color: OrcaTheme.accent) : null,
            onTap: () {
              ref.read(userProfileProvider.notifier).updateLanguage('te');
              Navigator.pop(ctx);
            },
          ),
        ],
      ),
    );
  }
}
