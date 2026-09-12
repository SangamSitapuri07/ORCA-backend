import '../../../../core/utils/date_formatter.dart';
import '../../domain/entities/alert_item.dart';

/// DTO for the ORCA Box alert contract.
class AlertDto {
  final String id;
  final String severity;
  final String title;
  final String? titleHi;
  final String message;
  final String? messageHi;
  final String source;
  final String? issuedAtStr;
  final String? expiresAtStr;
  final String? affectedArea;
  final bool? isActive;

  AlertDto({
    required this.id,
    required this.severity,
    required this.title,
    this.titleHi,
    required this.message,
    this.messageHi,
    required this.source,
    this.issuedAtStr,
    this.expiresAtStr,
    this.affectedArea,
    this.isActive,
  });

  factory AlertDto.fromJson(Map<String, dynamic> json) {
    final id = json['id'] as String?;
    final title = (json['title_en'] ?? json['title']) as String?;
    final message = (json['msg_en'] ?? json['message']) as String?;
    if (id == null || title == null || message == null) {
      throw const FormatException('Alert response is missing id, title, or message');
    }
    return AlertDto(
      id: id,
      severity: json['severity'] as String? ?? 'info',
      title: title,
      titleHi: json['title_hi'] as String?,
      message: message,
      messageHi: (json['msg_hi'] ?? json['message_hi']) as String?,
      source: json['source'] as String? ?? 'Unavailable',
      issuedAtStr: json['issued_at'] as String?,
      expiresAtStr: (json['valid_until'] ?? json['expires_at']) as String?,
      affectedArea: json['affected_area'] as String?,
      isActive: json['is_active'] as bool?,
    );
  }

  AlertItem toEntity() {
    final issuedAt = DateFormatter.parseIso(issuedAtStr) ??
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
    final expiresAt = DateFormatter.parseIso(expiresAtStr);
    return AlertItem(
      id: id,
      severity: severity,
      title: title,
      titleHi: titleHi,
      message: message,
      messageHi: messageHi,
      source: source,
      issuedAt: issuedAt,
      expiresAt: expiresAt,
      affectedArea: affectedArea,
      isActive: isActive ?? (expiresAt == null || expiresAt.isAfter(DateTime.now())),
    );
  }
}
