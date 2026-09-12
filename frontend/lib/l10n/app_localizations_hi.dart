// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Hindi (`hi`).
class AppLocalizationsHi extends AppLocalizations {
  AppLocalizationsHi([String locale = 'hi']) : super(locale);

  @override
  String get appName => 'ओरका (ORCA)';

  @override
  String get appTagline => 'समुद्री पारिस्थितिकी एवं मछुआरा सुरक्षा सलाहकार';

  @override
  String get tabHome => 'होम';

  @override
  String get tabMap => 'मानचित्र';

  @override
  String get tabAi => 'एआई एजेंट्स';

  @override
  String get tabAlerts => 'चेतावनी';

  @override
  String get tabNavigate => 'नेविगेट';

  @override
  String get tabInfo => 'जानकारी';

  @override
  String get verdictGo => 'सुरक्षित (GO)';

  @override
  String get verdictCaution => 'सावधानी (CAUTION)';

  @override
  String get verdictNoGo => 'खतरा - न जाएं (NO-GO)';

  @override
  String get verdictUnknown => 'अज्ञात स्थिति';

  @override
  String get canIGoTitle => 'क्या आज समुद्र में जा सकते हैं?';

  @override
  String get safeWindowLabel => 'सुरक्षित समय अवधि';

  @override
  String get noSafeWindow => 'अगले 48 घंटों में कोई सुरक्षित समय नहीं';

  @override
  String get variablesTitle => 'वर्तमान समुद्री स्थिति';

  @override
  String get hourlyForecastTitle => '48 घंटे लहरें एवं हवा का पूर्वानुमान';

  @override
  String get sourceLabel => 'स्रोत';

  @override
  String get dataFreshnessLabel => 'ताज़गी';

  @override
  String get freshStatus => 'ताज़ा (<30 मिनट)';

  @override
  String get recentStatus => 'हालिया (<3 घंटे)';

  @override
  String get staleStatus => 'पुरानी जानकारी';

  @override
  String get unreachableStatus => 'संपर्क नहीं हो सका';


  @override
  String get waveHeight => 'लहरों की ऊंचाई';

  @override
  String get windSpeed => 'हवा की गति';

  @override
  String get windGusts => 'हवा के झोंके';

  @override
  String get seaTemp => 'समुद्र का तापमान';

  @override
  String get oceanCurrent => 'समुद्री धारा';

  @override
  String get mapProbeTapPrompt =>
      'समुद्र में किसी भी स्थान पर क्लिक करके जानकारी देखें';

  @override
  String get mapLayersTitle => 'डेटा परतें';

  @override
  String get synopticOverlay => 'सिनोप्टिक मौसम दृश्य';

  @override
  String get locateMe => 'मेरी स्थिति';

  @override
  String get probeCoordinates => 'स्थान';

  @override
  String get probeChlorophyll => 'क्लोरोफिल (मछली क्षेत्र)';

  @override
  String get probeFishingEffort => 'मछली पकड़ने की गतिविधि';

  @override
  String get aiAgentsTitle => '11-चरण सहयोगी प्रणाली';

  @override
  String get aiRunAnalysis => '11-चरण विश्लेषण चलाएं';

  @override
  String get aiRunning => 'एजेंट्स मिलकर विश्लेषण कर रहे हैं...';

  @override
  String get aiCollaborationTrace => 'बैकएंड एजेंट ट्रेस';

  @override
  String get aiOrchestrationSynthesis => 'अंतिम निर्णय एवं निष्कर्ष';




  @override
  String get alertsTitle => 'सक्रिय समुद्री चेतावनी';

  @override
  String get noActiveAlerts => 'कोई सक्रिय तूफान या मौसम चेतावनी नहीं है';

  @override
  String get simulateAlert => 'चेतावनी सिमुलेशन (डेमो)';

  @override
  String get navigateTitle => 'मार्ग सुरक्षा एवं भूमि जांच';

  @override
  String get fromPort => 'प्रस्थान बंदरगाह / तट';

  @override
  String get toDestination => 'गंतव्य / मछली पकड़ने का क्षेत्र';

  @override
  String get checkRouteButton => 'मार्ग सुरक्षा जांचें';

  @override
  String get detourWaypoint => 'सुरक्षित मोड़ बिंदु (वेपॉइंट)';

  @override
  String get landVerifiedClear => 'भूमि जांच: रास्ता साफ है';

  @override
  String get landDetourRequired => 'मोड़ आवश्यक (भूमि से बचाव)';

  @override
  String get landBlocked => 'रास्ता भूमि से अवरुद्ध है';

  @override
  String get transitVerdict => 'यात्रा सुरक्षा निर्णय';

  @override
  String get infoTitle => 'सिस्टम जानकारी एवं स्रोत स्थिति';

  @override
  String get serverUrlLabel => 'ओरका बॉक्स सर्वर URL';

  @override
  String get serverUrlChange => 'सर्वर URL बदलें';

  @override
  String get serverUrlDialogTitle => 'सर्वर URL सेट करें';

  @override
  String get serverUrlHint => 'https://your-orca-box.example';

  @override
  String get checkHealthButton => 'डेटा स्रोतों की जांच करें';

  @override
  String get dataSourceCatalog => '14 बाहरी डेटा स्रोत';

  @override
  String get cacheManagement => 'लोकल स्टोरेज एवं कैश';

  @override
  String get clearCache => 'कैश डेटा साफ़ करें';


  @override
  String get languageLabel => 'भाषा / Language / భాష';

  @override
  String get aboutOrca => 'ORCA SIH26176 (ISRO) के बारे में';

  @override
  String get save => 'सहेजें';

  @override
  String get cancel => 'रद्द करें';

  @override
  String get retry => 'पुनः प्रयास करें';

  @override
  String get offlineBanner =>
      'आप ऑफ़लाइन हैं। उपलब्ध होने पर कैश की गई सलाह उसके मूल समय के साथ दिखाई जा रही है।';
}
