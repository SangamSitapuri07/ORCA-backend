import 'package:flutter/foundation.dart';
import '../cache/cache_service.dart';

class UserProfile {
  final String userId;
  final String displayName;
  final String preferredLanguage; // en, hi, te
  final String preferredFishingArea;
  final String homeHarbour;
  final String vesselType;
  final String? vesselRegistration;
  final Map<String, bool> notificationPreferences;

  const UserProfile({
    required this.userId,
    required this.displayName,
    required this.preferredLanguage,
    required this.preferredFishingArea,
    required this.homeHarbour,
    required this.vesselType,
    this.vesselRegistration,
    required this.notificationPreferences,
  });

  factory UserProfile.defaultGuest() {
    return const UserProfile(
      userId: 'local-guest',
      displayName: 'Guest fisher',
      preferredLanguage: 'en',
      preferredFishingArea: 'Not set',
      homeHarbour: 'Not set',
      vesselType: 'Not set',
      vesselRegistration: null,
      notificationPreferences: {
        'wave_alerts': true,
        'wind_alerts': true,
        'cyclone_alerts': true,
        'pfz_updates': true,
      },
    );
  }

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      userId: (json['user_id'] as String?) ?? 'local-guest',
      displayName: (json['display_name'] as String?) ?? 'Fisherman',
      preferredLanguage: (json['preferred_language'] as String?) ?? 'en',
      preferredFishingArea: (json['preferred_fishing_area'] as String?) ?? 'Not set',
      homeHarbour: (json['home_harbour'] as String?) ?? 'Not set',
      vesselType: (json['vessel_type'] as String?) ?? 'Not set',
      vesselRegistration: json['vessel_registration'] as String?,
      notificationPreferences: Map<String, bool>.from(
        (json['notification_preferences'] as Map?) ?? {
          'wave_alerts': true,
          'wind_alerts': true,
          'cyclone_alerts': true,
          'pfz_updates': true,
        },
      ),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'user_id': userId,
      'display_name': displayName,
      'preferred_language': preferredLanguage,
      'preferred_fishing_area': preferredFishingArea,
      'home_harbour': homeHarbour,
      'vessel_type': vesselType,
      'vessel_registration': vesselRegistration,
      'notification_preferences': notificationPreferences,
    };
  }

  UserProfile copyWith({
    String? displayName,
    String? preferredLanguage,
    String? preferredFishingArea,
    String? homeHarbour,
    String? vesselType,
    String? vesselRegistration,
    Map<String, bool>? notificationPreferences,
  }) {
    return UserProfile(
      userId: userId,
      displayName: displayName ?? this.displayName,
      preferredLanguage: preferredLanguage ?? this.preferredLanguage,
      preferredFishingArea: preferredFishingArea ?? this.preferredFishingArea,
      homeHarbour: homeHarbour ?? this.homeHarbour,
      vesselType: vesselType ?? this.vesselType,
      vesselRegistration: vesselRegistration ?? this.vesselRegistration,
      notificationPreferences: notificationPreferences ?? this.notificationPreferences,
    );
  }
}

/// On-device profile preferences only. This is not Supabase authentication.
/// Core safety advisories remain independent of cloud identity.
class LocalProfileService {
  final CacheService _cache;
  UserProfile _currentProfile;

  LocalProfileService(this._cache) : _currentProfile = UserProfile.defaultGuest() {
    _loadLocalSession();
  }

  UserProfile get currentProfile => _currentProfile;
  bool get isAuthenticated => false;

  void _loadLocalSession() {
    try {
      final cachedJson = _cache.get('auth.profile')?.data;
      if (cachedJson != null && cachedJson is Map<String, dynamic>) {
        _currentProfile = UserProfile.fromJson(cachedJson);
      }
    } catch (e) {
      debugPrint('Error loading cached profile: $e');
    }
  }

  Future<void> updateProfile(UserProfile newProfile) async {
    _currentProfile = newProfile;
    await _cache.set('auth.profile', newProfile.toJson());
  }

  Future<void> logout() async {
    _currentProfile = UserProfile.defaultGuest();
    await _cache.remove('auth.profile');
  }
}
