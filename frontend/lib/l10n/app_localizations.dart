import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_hi.dart';
import 'app_localizations_te.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('hi'),
    Locale('te')
  ];

  /// No description provided for @appName.
  ///
  /// In en, this message translates to:
  /// **'ORCA'**
  String get appName;

  /// No description provided for @appTagline.
  ///
  /// In en, this message translates to:
  /// **'Marine Ecosystem Reasoning with Collaborative Agents'**
  String get appTagline;

  /// No description provided for @tabHome.
  ///
  /// In en, this message translates to:
  /// **'Home'**
  String get tabHome;

  /// No description provided for @tabMap.
  ///
  /// In en, this message translates to:
  /// **'Map'**
  String get tabMap;

  /// No description provided for @tabAi.
  ///
  /// In en, this message translates to:
  /// **'AI Agents'**
  String get tabAi;

  /// No description provided for @tabAlerts.
  ///
  /// In en, this message translates to:
  /// **'Alerts'**
  String get tabAlerts;

  /// No description provided for @tabNavigate.
  ///
  /// In en, this message translates to:
  /// **'Navigate'**
  String get tabNavigate;

  /// No description provided for @tabInfo.
  ///
  /// In en, this message translates to:
  /// **'Info'**
  String get tabInfo;

  /// No description provided for @verdictGo.
  ///
  /// In en, this message translates to:
  /// **'GO SAFE'**
  String get verdictGo;

  /// No description provided for @verdictCaution.
  ///
  /// In en, this message translates to:
  /// **'CAUTION'**
  String get verdictCaution;

  /// No description provided for @verdictNoGo.
  ///
  /// In en, this message translates to:
  /// **'NO-GO DANGER'**
  String get verdictNoGo;

  /// No description provided for @verdictUnknown.
  ///
  /// In en, this message translates to:
  /// **'UNKNOWN'**
  String get verdictUnknown;

  /// No description provided for @canIGoTitle.
  ///
  /// In en, this message translates to:
  /// **'Can I Go Out to Sea?'**
  String get canIGoTitle;

  /// No description provided for @safeWindowLabel.
  ///
  /// In en, this message translates to:
  /// **'Safe Window'**
  String get safeWindowLabel;

  /// No description provided for @noSafeWindow.
  ///
  /// In en, this message translates to:
  /// **'No safe window in next 48 hours'**
  String get noSafeWindow;

  /// No description provided for @variablesTitle.
  ///
  /// In en, this message translates to:
  /// **'Current Conditions'**
  String get variablesTitle;

  /// No description provided for @hourlyForecastTitle.
  ///
  /// In en, this message translates to:
  /// **'48-Hour Wave & Wind Forecast'**
  String get hourlyForecastTitle;

  /// No description provided for @sourceLabel.
  ///
  /// In en, this message translates to:
  /// **'Source'**
  String get sourceLabel;

  /// No description provided for @dataFreshnessLabel.
  ///
  /// In en, this message translates to:
  /// **'Freshness'**
  String get dataFreshnessLabel;

  /// No description provided for @freshStatus.
  ///
  /// In en, this message translates to:
  /// **'Fresh (<30m)'**
  String get freshStatus;

  /// No description provided for @recentStatus.
  ///
  /// In en, this message translates to:
  /// **'Recent (<3h)'**
  String get recentStatus;

  /// No description provided for @staleStatus.
  ///
  /// In en, this message translates to:
  /// **'Stale'**
  String get staleStatus;

  /// No description provided for @unreachableStatus.
  ///
  /// In en, this message translates to:
  /// **'Unreachable'**
  String get unreachableStatus;


  /// No description provided for @waveHeight.
  ///
  /// In en, this message translates to:
  /// **'Wave Height'**
  String get waveHeight;

  /// No description provided for @windSpeed.
  ///
  /// In en, this message translates to:
  /// **'Wind Speed'**
  String get windSpeed;

  /// No description provided for @windGusts.
  ///
  /// In en, this message translates to:
  /// **'Wind Gusts'**
  String get windGusts;

  /// No description provided for @seaTemp.
  ///
  /// In en, this message translates to:
  /// **'Sea Surface Temp'**
  String get seaTemp;

  /// No description provided for @oceanCurrent.
  ///
  /// In en, this message translates to:
  /// **'Ocean Current'**
  String get oceanCurrent;

  /// No description provided for @mapProbeTapPrompt.
  ///
  /// In en, this message translates to:
  /// **'Tap any ocean point on the map to probe conditions'**
  String get mapProbeTapPrompt;

  /// No description provided for @mapLayersTitle.
  ///
  /// In en, this message translates to:
  /// **'Data Layers'**
  String get mapLayersTitle;

  /// No description provided for @synopticOverlay.
  ///
  /// In en, this message translates to:
  /// **'Synoptic Weather Overlay'**
  String get synopticOverlay;

  /// No description provided for @locateMe.
  ///
  /// In en, this message translates to:
  /// **'Locate Me'**
  String get locateMe;

  /// No description provided for @probeCoordinates.
  ///
  /// In en, this message translates to:
  /// **'Location'**
  String get probeCoordinates;

  /// No description provided for @probeChlorophyll.
  ///
  /// In en, this message translates to:
  /// **'Chlorophyll-a'**
  String get probeChlorophyll;

  /// No description provided for @probeFishingEffort.
  ///
  /// In en, this message translates to:
  /// **'Fishing Effort'**
  String get probeFishingEffort;

  /// No description provided for @aiAgentsTitle.
  ///
  /// In en, this message translates to:
  /// **'Collaborative Multi-Agent System'**
  String get aiAgentsTitle;

  /// No description provided for @aiRunAnalysis.
  ///
  /// In en, this message translates to:
  /// **'Run 10-Agent Analysis'**
  String get aiRunAnalysis;

  /// No description provided for @aiRunning.
  ///
  /// In en, this message translates to:
  /// **'Agents collaborating...'**
  String get aiRunning;

  /// No description provided for @aiCollaborationTrace.
  ///
  /// In en, this message translates to:
  /// **'Live Agent Collaboration Trace'**
  String get aiCollaborationTrace;

  /// No description provided for @aiOrchestrationSynthesis.
  ///
  /// In en, this message translates to:
  /// **'Orchestrator Synthesis'**
  String get aiOrchestrationSynthesis;

  /// No description provided for @aiChatTitle.
  ///
  /// In en, this message translates to:
  /// **'Marine Advisory Assistant'**
  String get aiChatTitle;

  /// No description provided for @aiChatUnavailable.
  ///
  /// In en, this message translates to:
  /// **'Ollama LLM chat is currently paused by design choice to conserve edge resources.'**
  String get aiChatUnavailable;

  /// No description provided for @aiChatInputHint.
  ///
  /// In en, this message translates to:
  /// **'Ask about ocean conditions...'**
  String get aiChatInputHint;

  /// No description provided for @alertsTitle.
  ///
  /// In en, this message translates to:
  /// **'Active Marine Alerts'**
  String get alertsTitle;

  /// No description provided for @noActiveAlerts.
  ///
  /// In en, this message translates to:
  /// **'No active weather or cyclone warnings'**
  String get noActiveAlerts;

  /// No description provided for @simulateAlert.
  ///
  /// In en, this message translates to:
  /// **'Simulate Alert (Demo)'**
  String get simulateAlert;

  /// No description provided for @navigateTitle.
  ///
  /// In en, this message translates to:
  /// **'Route Safety & Land Check'**
  String get navigateTitle;

  /// No description provided for @fromPort.
  ///
  /// In en, this message translates to:
  /// **'Departure Port / Point'**
  String get fromPort;

  /// No description provided for @toDestination.
  ///
  /// In en, this message translates to:
  /// **'Destination / Fishing Spot'**
  String get toDestination;

  /// No description provided for @checkRouteButton.
  ///
  /// In en, this message translates to:
  /// **'Verify Route Safety'**
  String get checkRouteButton;

  /// No description provided for @detourWaypoint.
  ///
  /// In en, this message translates to:
  /// **'Detour Waypoint'**
  String get detourWaypoint;

  /// No description provided for @landVerifiedClear.
  ///
  /// In en, this message translates to:
  /// **'Land Check: Verified Clear'**
  String get landVerifiedClear;

  /// No description provided for @landDetourRequired.
  ///
  /// In en, this message translates to:
  /// **'Detour Required (Avoids Land)'**
  String get landDetourRequired;

  /// No description provided for @landBlocked.
  ///
  /// In en, this message translates to:
  /// **'Route Blocked by Land'**
  String get landBlocked;

  /// No description provided for @transitVerdict.
  ///
  /// In en, this message translates to:
  /// **'Transit Safety Verdict'**
  String get transitVerdict;

  /// No description provided for @infoTitle.
  ///
  /// In en, this message translates to:
  /// **'System Info & Data Health'**
  String get infoTitle;

  /// No description provided for @serverUrlLabel.
  ///
  /// In en, this message translates to:
  /// **'ORCA Box Server URL'**
  String get serverUrlLabel;

  /// No description provided for @serverUrlChange.
  ///
  /// In en, this message translates to:
  /// **'Change Server URL'**
  String get serverUrlChange;

  /// No description provided for @serverUrlDialogTitle.
  ///
  /// In en, this message translates to:
  /// **'Configure Server URL'**
  String get serverUrlDialogTitle;

  /// No description provided for @serverUrlHint.
  ///
  /// In en, this message translates to:
  /// **'https://your-orca-box.example'**
  String get serverUrlHint;

  /// No description provided for @checkHealthButton.
  ///
  /// In en, this message translates to:
  /// **'Check Data Sources Health'**
  String get checkHealthButton;

  /// No description provided for @dataSourceCatalog.
  ///
  /// In en, this message translates to:
  /// **'14 External Data Sources'**
  String get dataSourceCatalog;

  /// No description provided for @cacheManagement.
  ///
  /// In en, this message translates to:
  /// **'Local Storage & Cache'**
  String get cacheManagement;

  /// No description provided for @clearCache.
  ///
  /// In en, this message translates to:
  /// **'Clear Cached Data'**
  String get clearCache;


  /// No description provided for @languageLabel.
  ///
  /// In en, this message translates to:
  /// **'Language / भाषा / భాష'**
  String get languageLabel;

  /// No description provided for @aboutOrca.
  ///
  /// In en, this message translates to:
  /// **'About ORCA SIH26176 (ISRO)'**
  String get aboutOrca;

  /// No description provided for @save.
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get save;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @retry.
  ///
  /// In en, this message translates to:
  /// **'Retry'**
  String get retry;

  /// No description provided for @offlineBanner.
  ///
  /// In en, this message translates to:
  /// **'You are offline. Showing last verified cached advisory.'**
  String get offlineBanner;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'hi', 'te'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'hi':
      return AppLocalizationsHi();
    case 'te':
      return AppLocalizationsTe();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
