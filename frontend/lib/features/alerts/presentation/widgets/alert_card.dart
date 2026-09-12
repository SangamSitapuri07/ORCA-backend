import 'package:flutter/material.dart';
import '../../../../core/theme/orca_theme.dart';
import '../../../../core/theme/verdict_colors.dart';
import '../../../../core/utils/date_formatter.dart';
import '../../domain/entities/alert_item.dart';

/// Card rendering an active marine alert (§8, §19).
class AlertCard extends StatelessWidget {
  final AlertItem alert;

  const AlertCard({
    super.key,
    required this.alert,
  });

  @override
  Widget build(BuildContext context) {
    final color = VerdictColors.fromVerdict(alert.severity);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      margin: const EdgeInsets.symmetric(vertical: 6),
      decoration: BoxDecoration(
        color: OrcaTheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color, width: 1.4),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: 0.15),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: Icon + Title + Severity Pill
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                VerdictColors.iconForVerdict(alert.severity),
                color: color,
                size: 24,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      alert.title,
                      style: const TextStyle(
                        fontSize: 14.5,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                    if (alert.titleHi != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        alert.titleHi!,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: Colors.white.withValues(alpha: 0.8),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  alert.severity.toUpperCase(),
                  style: TextStyle(
                    color: color,
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),

          // Message Body
          Text(
            alert.message,
            style: const TextStyle(
              fontSize: 12.5,
              color: OrcaTheme.textPrimary,
              height: 1.35,
            ),
          ),
          if (alert.messageHi != null) ...[
            const SizedBox(height: 6),
            Text(
              alert.messageHi!,
              style: TextStyle(
                fontSize: 12,
                color: Colors.white.withValues(alpha: 0.75),
                height: 1.3,
              ),
            ),
          ],
          const SizedBox(height: 12),
          const Divider(color: OrcaTheme.cardBorder, height: 1),
          const SizedBox(height: 8),

          // Footer: Source + Issued Time + Affected Area
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  '${alert.source} · ${DateFormatter.formatIstTime(alert.issuedAt)}',
                  style: const TextStyle(
                    fontSize: 11,
                    color: OrcaTheme.textMuted,
                    fontWeight: FontWeight.w500,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (alert.affectedArea != null) ...[
                Text(
                  alert.affectedArea!,
                  style: const TextStyle(
                    fontSize: 10.5,
                    color: OrcaTheme.textSecondary,
                    fontWeight: FontWeight.w500,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}
