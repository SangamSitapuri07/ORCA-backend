import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'core/theme/orca_theme.dart';
import 'core/theme/verdict_colors.dart';
import 'core/cache/cache_service.dart';
import 'features/advisory/presentation/screens/home_screen.dart';
import 'features/agents/presentation/screens/ai_screen.dart';
import 'features/alerts/presentation/providers/alerts_provider.dart';
import 'features/alerts/presentation/screens/alerts_screen.dart';
import 'features/map/presentation/screens/map_screen.dart';
import 'features/navigate/presentation/screens/navigate_screen.dart';
import 'features/onboarding/presentation/screens/onboarding_screen.dart';
import 'features/settings/presentation/providers/settings_provider.dart';
import 'features/settings/presentation/screens/info_screen.dart';
import 'features/auth/presentation/screens/profile_screen.dart';
import 'features/locations/presentation/screens/saved_locations_screen.dart';
import 'features/history/presentation/screens/history_screen.dart';
import 'features/catch_reports/presentation/screens/catch_report_screen.dart';
import 'features/official/presentation/screens/official_dashboard_screen.dart';
import 'l10n/app_localizations.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final onboarding = ref.watch(cacheServiceProvider).get('app.onboarding')?.data['complete'] == true;
  return GoRouter(
    initialLocation: onboarding ? '/home' : '/onboarding',
    routes: [
      ShellRoute(
        builder: (context, state, child) {
          return OrcaNavigationScaffold(child: child);
        },
        routes: [
          GoRoute(
            path: '/home',
            builder: (context, state) => const HomeScreen(),
          ),
          GoRoute(
            path: '/map',
            builder: (context, state) => const MapScreen(),
          ),
          GoRoute(
            path: '/ai',
            builder: (context, state) => const AiScreen(),
          ),
          GoRoute(
            path: '/alerts',
            builder: (context, state) => const AlertsScreen(),
          ),
          GoRoute(
            path: '/navigate',
            builder: (context, state) => const NavigateScreen(),
          ),
          GoRoute(
            path: '/info',
            builder: (context, state) => const InfoScreen(),
          ),
          GoRoute(
            path: '/profile',
            builder: (context, state) => const ProfileScreen(),
          ),
          GoRoute(
            path: '/locations',
            builder: (context, state) => const SavedLocationsScreen(),
          ),
          GoRoute(
            path: '/history',
            builder: (context, state) => const HistoryScreen(),
          ),
          GoRoute(
            path: '/catch-report',
            builder: (context, state) => const CatchReportScreen(),
          ),
          GoRoute(
            path: '/official-dashboard',
            builder: (context, state) => const OfficialDashboardScreen(),
          ),
        ],
      ),
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => OnboardingScreen(
          onFinish: () => context.go('/home'),
        ),
      ),
    ],
  );
});

/// Main App widget configuring GoRouter, Dark Theme, and Localization (§10).
class OrcaApp extends ConsumerWidget {
  const OrcaApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final selectedLocale = ref.watch(selectedLocaleProvider);

    return MaterialApp.router(
      title: 'ORCA — Marine Advisory',
      debugShowCheckedModeBanner: false,
      theme: OrcaTheme.darkTheme,
      routerConfig: router,
      locale: Locale(selectedLocale),
      supportedLocales: const [
        Locale('en'),
        Locale('hi'),
        Locale('te'),
      ],
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
    );
  }
}

/// 6-Tab Bottom Navigation Scaffold (§8, §10).
class OrcaNavigationScaffold extends ConsumerWidget {
  final Widget child;

  const OrcaNavigationScaffold({
    super.key,
    required this.child,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alertsCount = ref.watch(alertsProvider).valueOrNull?.length ?? 0;
    final location = GoRouterState.of(context).matchedLocation;
    final selectedIndex = _calculateSelectedIndex(location);

    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: (index) {
          switch (index) {
            case 0:
              context.go('/home');
              break;
            case 1:
              context.go('/map');
              break;
            case 2:
              context.go('/ai');
              break;
            case 3:
              context.go('/alerts');
              break;
            case 4:
              context.go('/navigate');
              break;
            case 5:
              context.go('/info');
              break;
          }
        },
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.shield_outlined),
            selectedIcon: Icon(Icons.shield),
            label: 'Home',
          ),
          const NavigationDestination(
            icon: Icon(Icons.map_outlined),
            selectedIcon: Icon(Icons.map),
            label: 'Map',
          ),
          const NavigationDestination(
            icon: Icon(Icons.hub_outlined),
            selectedIcon: Icon(Icons.hub),
            label: 'AI Trace',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: alertsCount > 0,
              label: Text('$alertsCount'),
              backgroundColor: VerdictColors.noGo,
              child: const Icon(Icons.notifications_outlined),
            ),
            selectedIcon: Badge(
              isLabelVisible: alertsCount > 0,
              label: Text('$alertsCount'),
              backgroundColor: VerdictColors.noGo,
              child: const Icon(Icons.notifications),
            ),
            label: 'Alerts',
          ),
          const NavigationDestination(
            icon: Icon(Icons.directions_boat_outlined),
            selectedIcon: Icon(Icons.directions_boat),
            label: 'Navigate',
          ),
          const NavigationDestination(
            icon: Icon(Icons.info_outline),
            selectedIcon: Icon(Icons.info),
            label: 'Info',
          ),
        ],
      ),
    );
  }

  int _calculateSelectedIndex(String location) {
    if (location.startsWith('/home')) return 0;
    if (location.startsWith('/map')) return 1;
    if (location.startsWith('/ai')) return 2;
    if (location.startsWith('/alerts')) return 3;
    if (location.startsWith('/navigate')) return 4;
    if (location.startsWith('/info')) return 5;
    return 0;
  }
}
