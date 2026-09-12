import 'package:flutter/material.dart';

/// Single source of truth for all verdict, severity, and ocean tokens (§15).
class VerdictColors {
  /// 🟢 GO SAFE (#4ade80)
  static const Color go = Color(0xFF4ADE80);

  /// 🟠 CAUTION (#fbbf24)
  static const Color caution = Color(0xFFFBBF24);

  /// 🔴 NO-GO / DANGER (#f87171)
  static const Color noGo = Color(0xFFF87171);

  /// 🔵 INFO (#22d3ee)
  static const Color info = Color(0xFF22D3EE);

  /// 🚨 CRITICAL (#ef4444)
  static const Color critical = Color(0xFFEF4444);

  /// ⚪ STALE BADGE (#94a3b8)
  static const Color stale = Color(0xFF94A3B8);

  /// ⛰️ LAND MASK TONE (#2e4066)
  static const Color land = Color(0xFF2E4066);

  /// 🌊 SEA DEEP TONE (#0d3a63)
  static const Color sea = Color(0xFF0D3A63);

  // Background card tints for verdicts
  static const Color goBg = Color(0xFF0F3823);
  static const Color cautionBg = Color(0xFF3B2E0B);
  static const Color noGoBg = Color(0xFF3B1414);
  static const Color infoBg = Color(0xFF0C2C38);

  /// Maps string verdict to Color.
  static Color fromVerdict(String? verdict) {
    if (verdict == null) return stale;
    final lower = verdict.toLowerCase().replaceAll('-', '_');
    if (lower.contains('go') && !lower.contains('no_go') && !lower.contains('nogo')) {
      return go;
    }
    if (lower.contains('caution') || lower.contains('mod') || lower.contains('warning')) {
      return caution;
    }
    if (lower.contains('no_go') || lower.contains('nogo') || lower.contains('danger') || lower.contains('crit')) {
      return noGo;
    }
    if (lower.contains('info')) {
      return info;
    }
    return stale;
  }

  /// Maps string verdict to Card Background tint.
  static Color backgroundFromVerdict(String? verdict) {
    if (verdict == null) return const Color(0xFF1E293B);
    final lower = verdict.toLowerCase().replaceAll('-', '_');
    if (lower.contains('go') && !lower.contains('no_go') && !lower.contains('nogo')) {
      return goBg;
    }
    if (lower.contains('caution') || lower.contains('mod')) {
      return cautionBg;
    }
    if (lower.contains('no_go') || lower.contains('nogo') || lower.contains('danger')) {
      return noGoBg;
    }
    return const Color(0xFF1E293B);
  }

  /// Shape icon for low-literacy clarity (§7).
  static IconData iconForVerdict(String? verdict) {
    if (verdict == null) return Icons.help_outline;
    final lower = verdict.toLowerCase().replaceAll('-', '_');
    if (lower.contains('go') && !lower.contains('no_go') && !lower.contains('nogo')) {
      return Icons.check_circle; // ✔ ●
    }
    if (lower.contains('caution') || lower.contains('mod')) {
      return Icons.warning_rounded; // ⚠ ▲
    }
    if (lower.contains('no_go') || lower.contains('nogo') || lower.contains('danger')) {
      return Icons.dangerous; // ⛔ ■
    }
    return Icons.info_outline;
  }
}
