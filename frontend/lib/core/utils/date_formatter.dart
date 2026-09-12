import 'package:intl/intl.dart';

/// Date, timestamp, and relative age formatting helpers.
class DateFormatter {
  /// Formats UTC/Local timestamp to IST string ("11:26 IST").
  static String formatIstTime(DateTime dateTime) {
    // Convert to IST (+5:30)
    final ist = dateTime.toUtc().add(const Duration(hours: 5, minutes: 30));
    final formatter = DateFormat('HH:mm');
    return '${formatter.format(ist)} IST';
  }

  /// Parses ISO8601 string safely.
  static DateTime? parseIso(dynamic value) {
    if (value == null) return null;
    if (value is DateTime) return value;
    if (value is String) {
      try {
        return DateTime.parse(value);
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  /// Relative timeago description, e.g. "12 min ago" or "4 hours ago".
  static String timeAgo(DateTime dateTime) {
    final now = DateTime.now();
    final difference = now.difference(dateTime);

    if (difference.inSeconds < 60) {
      return 'Just now';
    } else if (difference.inMinutes < 60) {
      return '${difference.inMinutes} min ago';
    } else if (difference.inHours < 24) {
      return '${difference.inHours} hr ago';
    } else {
      return '${difference.inDays} days ago';
    }
  }
}
