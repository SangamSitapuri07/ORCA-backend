import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/network/dio_provider.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/theme/orca_theme.dart';

/// Modal dialog for user-configured base URL (§2, §8).
class ServerConfigDialog extends ConsumerStatefulWidget {
  const ServerConfigDialog({super.key});

  @override
  ConsumerState<ServerConfigDialog> createState() => _ServerConfigDialogState();
}

class _ServerConfigDialogState extends ConsumerState<ServerConfigDialog> {
  late TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    final currentUrl = ref.read(baseUrlProvider);
    _controller = TextEditingController(text: currentUrl);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: OrcaTheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: OrcaTheme.cardBorder),
      ),
      title: const Row(
        children: [
          Icon(Icons.dns, color: OrcaTheme.accent, size: 22),
          SizedBox(width: 8),
          Text(
            'ORCA Box Server URL',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
          ),
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Enter the IP address of your running ORCA Box mini-PC/laptop on the local WiFi hotspot or LAN:',
            style: TextStyle(fontSize: 12, color: OrcaTheme.textSecondary),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _controller,
            style: const TextStyle(color: Colors.white, fontSize: 13),
            decoration: InputDecoration(
              filled: true,
              fillColor: OrcaTheme.surfaceElevated,
              hintText: 'https://your-orca-box.example',
              hintStyle: const TextStyle(color: OrcaTheme.textMuted),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: OrcaTheme.cardBorder),
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Release builds require HTTPS. For local debug builds, inject the emulator or LAN URL with --dart-define=ORCA_API_BASE_URL=…',
            style: TextStyle(fontSize: 11, color: OrcaTheme.textMuted),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel', style: TextStyle(color: OrcaTheme.textSecondary)),
        ),
        ElevatedButton(
          onPressed: () async {
            final text = _controller.text.trim().replaceFirst(RegExp(r'/$'), '');
            final uri = Uri.tryParse(text);
            final valid = uri != null && uri.hasScheme && uri.host.isNotEmpty &&
                (uri.scheme == 'https' || (!kReleaseMode && uri.scheme == 'http'));
            if (!valid) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Enter a valid ORCA Box URL. Release builds require HTTPS.')),
              );
              return;
            }
            ref.read(baseUrlProvider.notifier).state = text;
            await ref.read(cacheServiceProvider).put(
              'settings.base_url',
              <String, dynamic>{'value': text},
              ttl: const Duration(days: 3650),
            );
            if (!context.mounted) return;
            Navigator.of(context).pop();
          },
          style: ElevatedButton.styleFrom(
            backgroundColor: OrcaTheme.accent,
            foregroundColor: Colors.black,
          ),
          child: const Text('Save URL'),
        ),
      ],
    );
  }
}
