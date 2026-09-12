import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/cache/cache_service.dart';
import '../../../../core/auth/local_profile_service.dart';

final localProfileServiceProvider = Provider<LocalProfileService>((ref) {
  final cache = ref.watch(cacheServiceProvider);
  return LocalProfileService(cache);
});

final userProfileProvider = StateNotifierProvider<UserProfileNotifier, UserProfile>((ref) {
  final authService = ref.watch(localProfileServiceProvider);
  return UserProfileNotifier(authService);
});

class UserProfileNotifier extends StateNotifier<UserProfile> {
  final LocalProfileService _authService;

  UserProfileNotifier(this._authService) : super(_authService.currentProfile);

  Future<void> updateDisplayName(String name) async {
    final updated = state.copyWith(displayName: name);
    state = updated;
    await _authService.updateProfile(updated);
  }

  Future<void> updateLanguage(String lang) async {
    final updated = state.copyWith(preferredLanguage: lang);
    state = updated;
    await _authService.updateProfile(updated);
  }

  Future<void> updateHomeHarbour(String harbour) async {
    final updated = state.copyWith(homeHarbour: harbour);
    state = updated;
    await _authService.updateProfile(updated);
  }

  Future<void> updateVessel(String vesselType, String? reg) async {
    final updated = state.copyWith(vesselType: vesselType, vesselRegistration: reg);
    state = updated;
    await _authService.updateProfile(updated);
  }

  Future<void> toggleNotification(String key, bool enabled) async {
    final prefs = Map<String, bool>.from(state.notificationPreferences);
    prefs[key] = enabled;
    final updated = state.copyWith(notificationPreferences: prefs);
    state = updated;
    await _authService.updateProfile(updated);
  }
}
