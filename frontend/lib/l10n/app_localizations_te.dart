// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Telugu (`te`).
class AppLocalizationsTe extends AppLocalizations {
  AppLocalizationsTe([String locale = 'te']) : super(locale);

  @override
  String get appName => 'ఓర్కా (ORCA)';

  @override
  String get appTagline =>
      'సముద్ర పర్యావరణ వ్యవస్థ మరియు మత్స్యకారుల భద్రతా సలహాదారు';

  @override
  String get tabHome => 'హోమ్';

  @override
  String get tabMap => 'మ్యాప్';

  @override
  String get tabAi => 'ఏఐ ఏజెంట్లు';

  @override
  String get tabAlerts => 'హెచ్చరికలు';

  @override
  String get tabNavigate => 'మార్గం';

  @override
  String get tabInfo => 'సమాచారం';

  @override
  String get verdictGo => 'సురక్షితం (వెళ్ళవచ్చు)';

  @override
  String get verdictCaution => 'జాగ్రత్త (CAUTION)';

  @override
  String get verdictNoGo => 'ప్రమాదం (వెళ్లవద్దు)';

  @override
  String get verdictUnknown => 'తెలియదు';

  @override
  String get canIGoTitle => 'ఈ రోజు వేటకు వెళ్ళవచ్చా?';

  @override
  String get safeWindowLabel => 'సురక్షిత సమయం';

  @override
  String get noSafeWindow => 'రాబోయే 48 గంటల్లో సురక్షిత సమయం లేదు';

  @override
  String get variablesTitle => 'ప్రస్తుత సముద్ర పరిస్థితులు';

  @override
  String get hourlyForecastTitle => '48 గంటల అలలు & గాలి అంచనా';

  @override
  String get sourceLabel => 'మూలం';

  @override
  String get dataFreshnessLabel => 'తాజాదనం';

  @override
  String get freshStatus => 'తాజా (<30ని)';

  @override
  String get recentStatus => 'ఇటీవలి (<3గం)';

  @override
  String get staleStatus => 'పాత సమాచారం';

  @override
  String get unreachableStatus => 'అందుబాటులో లేదు';


  @override
  String get waveHeight => 'అలల ఎత్తు';

  @override
  String get windSpeed => 'గాలి వేగం';

  @override
  String get windGusts => 'ఈదురు గాలులు';

  @override
  String get seaTemp => 'సముద్ర ఉపరితల ఉష్ణోగ్రత';

  @override
  String get oceanCurrent => 'సముద్ర ప్రవాహం';

  @override
  String get mapProbeTapPrompt =>
      'పరిస్థితులను చూడటానికి సముద్రంలో ఎక్కడైనా తాకండి';

  @override
  String get mapLayersTitle => 'డేటా లేయర్లు';

  @override
  String get synopticOverlay => 'వాతావరణ మ్యాప్';

  @override
  String get locateMe => 'నా స్థానం';

  @override
  String get probeCoordinates => 'స్థానం';

  @override
  String get probeChlorophyll => 'క్లోరోఫిల్ (చేపల ప్రాంతం)';

  @override
  String get probeFishingEffort => 'చేపల వేట కార్యకలాపాలు';

  @override
  String get aiAgentsTitle => '10-ఏజెంట్ల సమన్వయ వ్యవస్థ';

  @override
  String get aiRunAnalysis => '10-ఏజెంట్ విశ్లేషణ ప్రారంభించు';

  @override
  String get aiRunning => 'ఏజెంట్లు విశ్లేషిస్తున్నారు...';

  @override
  String get aiCollaborationTrace => 'ఏజెంట్ సమన్వయ లైవ్ ట్రేస్';

  @override
  String get aiOrchestrationSynthesis => 'తుది నిర్ణయం మరియు ముగింపు';

  @override
  String get aiChatTitle => 'సముద్ర సలహాదారు సహాయకుడు';

  @override
  String get aiChatUnavailable =>
      'ఎడ్జ్ సర్వర్ వనరులను ఆదా చేయడానికి చాట్ ప్రస్తుతం తాత్కాలికంగా నిలిపివేయబడింది.';

  @override
  String get aiChatInputHint => 'సముద్ర వాతావరణం గురించి అడగండి...';

  @override
  String get alertsTitle => 'సక్రియ హెచ్చరికలు';

  @override
  String get noActiveAlerts =>
      'ప్రస్తుతం ఎలాంటి తుఫాను లేదా వాతావరణ హెచ్చరికలు లేవు';

  @override
  String get simulateAlert => 'హెచ్చరిక అనుకరణ (డెమో)';

  @override
  String get navigateTitle => 'మార్గ భద్రత & భూమి తనిఖీ';

  @override
  String get fromPort => 'బయలుదేరే రేవు / తీరం';

  @override
  String get toDestination => 'గమ్యస్థానం / చేపల వేట ప్రాంతం';

  @override
  String get checkRouteButton => 'మార్గ భద్రతను తనిఖీ చేయండి';

  @override
  String get detourWaypoint => 'సురక్షిత మలుపు బిందువు';

  @override
  String get landVerifiedClear => 'భూమి తనిఖీ: మార్గం స్పష్టంగా ఉంది';

  @override
  String get landDetourRequired => 'మలుపు అవసరం (భూమిని నివారించడానికి)';

  @override
  String get landBlocked => 'భూమి వల్ల మార్గం మూసివేయబడింది';

  @override
  String get transitVerdict => 'ప్రయాణ భద్రతా నిర్ణయం';

  @override
  String get infoTitle => 'సిస్టమ్ సమాచారం & డేటా స్థితి';

  @override
  String get serverUrlLabel => 'ఓర్కా బాక్స్ సర్వర్ URL';

  @override
  String get serverUrlChange => 'సర్వర్ URL మార్చండి';

  @override
  String get serverUrlDialogTitle => 'సర్వర్ URL అమర్చండి';

  @override
  String get serverUrlHint =>
      'https://your-orca-box.example';

  @override
  String get checkHealthButton => 'డేటా మూలాల స్థితిని తనిఖీ చేయండి';

  @override
  String get dataSourceCatalog => '14 బాహ్య డేటా మూలాలు';

  @override
  String get cacheManagement => 'లోకల్ స్టోరేజ్ & కాష్';

  @override
  String get clearCache => 'కాష్ డేటాను తొలగించండి';


  @override
  String get languageLabel => 'భాష / Language / भाषा';

  @override
  String get aboutOrca => 'ORCA SIH26176 (ISRO) గురించి';

  @override
  String get save => 'సేవ్ చేయండి';

  @override
  String get cancel => 'రద్దు చేయండి';

  @override
  String get retry => 'మళ్ళీ ప్రయత్నించండి';

  @override
  String get offlineBanner =>
      'మీరు ఆఫ్‌లైన్‌లో ఉన్నారు. చివరి ధృవీకరించిన సలహా చూపబడుతోంది.';
}
