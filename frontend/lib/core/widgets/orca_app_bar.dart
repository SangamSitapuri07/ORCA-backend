import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../live/live_channel.dart';
import '../theme/orca_theme.dart';
import '../theme/verdict_colors.dart';

/// Custom top app bar with the live SSE indicator.
class OrcaAppBar extends ConsumerWidget implements PreferredSizeWidget {
  final String title;
  final String? subtitle;
  final List<Widget>? actions;

  const OrcaAppBar({
    super.key,
    required this.title,
    this.subtitle,
    this.actions,
  });

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight + 6);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final liveStatus = ref.watch(liveChannelProvider);

    return AppBar(
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 2),
            Text(
              subtitle!,
              style: const TextStyle(
                fontSize: 11,
                color: OrcaTheme.textSecondary,
                fontWeight: FontWeight.w400,
              ),
            ),
          ],
        ],
      ),
      actions: [
        // Live SSE connection status dot
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8.0),
          child: Tooltip(
            message: 'Live stream: ${liveStatus.name}',
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: _statusColor(liveStatus),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: _statusColor(liveStatus).withValues(alpha: 0.6),
                        blurRadius: 4,
                        spreadRadius: 1,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 5),
                Text(
                  liveStatus == LiveStreamStatus.connected
                      ? 'LIVE'
                      : liveStatus == LiveStreamStatus.disconnected ? 'OFFLINE' : 'WAIT',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                    color: _statusColor(liveStatus),
                    letterSpacing: 0.5,
                  ),
                ),
              ],
            ),
          ),
        ),
        if (actions != null) ...actions!,
      ],
    );
  }

  Color _statusColor(LiveStreamStatus status) {
    switch (status) {
      case LiveStreamStatus.connected:
        return VerdictColors.go;
      case LiveStreamStatus.connecting:
      case LiveStreamStatus.reconnecting:
        return VerdictColors.caution;
      case LiveStreamStatus.disconnected:
        return VerdictColors.stale;
    }
  }
}
