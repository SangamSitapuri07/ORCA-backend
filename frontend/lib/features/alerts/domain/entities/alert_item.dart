/// Domain entity representing a severe marine alert or cyclone warning (§4, §8, §19).
class AlertItem {
  final String id;
  final String severity; // info, caution, danger, critical
  final String title;
  final String? titleHi;
  final String message;
  final String? messageHi;
  final String source;
  final DateTime issuedAt;
  final DateTime? expiresAt;
  final String? affectedArea;
  final bool isActive;

  const AlertItem({
    required this.id,
    required this.severity,
    required this.title,
    this.titleHi,
    required this.message,
    this.messageHi,
    required this.source,
    required this.issuedAt,
    this.expiresAt,
    this.affectedArea,
    required this.isActive,
  });
}
