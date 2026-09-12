import 'package:flutter/material.dart';
import '../theme/verdict_colors.dart';

/// Classification of agent execution type (§3).
enum AgentClass {
  deterministic,
  llm,
}

/// Descriptor model representing an agent from the authoritative registry.
class AgentDescriptor {
  final String id;
  final String emoji;
  final String name;
  final AgentClass agentClass;
  final String blurb;
  final Color accentColor;
  final List<String> defaultSources;

  const AgentDescriptor({
    required this.id,
    required this.emoji,
    required this.name,
    required this.agentClass,
    required this.blurb,
    required this.accentColor,
    this.defaultSources = const <String>[],
  });

  bool get isDeterministic => agentClass == AgentClass.deterministic;
  bool get isLlm => agentClass == AgentClass.llm;

  String get classLabel => isDeterministic ? 'DETERMINISTIC' : 'LLM AGENT';
}

/// Authoritative 11-agent registry mirroring backend (§3, §11).
class AgentRegistry {
  static const List<AgentDescriptor> all = <AgentDescriptor>[
    AgentDescriptor(
      id: 'data_validation',
      emoji: '✅',
      name: 'Data Validation',
      agentClass: AgentClass.deterministic,
      blurb: 'QC gate: validates physical ranges, missing values, timestamps, and lag chains across all feeds.',
      accentColor: VerdictColors.go,
      defaultSources: <String>['Open-Meteo', 'NOAA', 'INCOIS', 'MOSDAC'],
    ),
    AgentDescriptor(
      id: 'gis_spatial',
      emoji: '🗺️',
      name: 'GIS & Spatial',
      agentClass: AgentClass.deterministic,
      blurb: 'Checks GLOBE land/sea context. Authoritative EEZ, protected-area, restricted-zone, and chart polygons are not integrated.',
      accentColor: VerdictColors.info,
      defaultSources: <String>['GLOBE 1 km land mask', 'ORCA static port references (citations pending)'],
    ),
    AgentDescriptor(
      id: 'ocean_analysis',
      emoji: '🌊',
      name: 'Ocean Analysis',
      agentClass: AgentClass.llm,
      blurb: 'Reports SST context and checks short-term wave evidence against ORCA Phase-1 thresholds.',
      accentColor: VerdictColors.sea,
      defaultSources: <String>['Open-Meteo Marine (MFWAM/ECMWF)'],
    ),
    AgentDescriptor(
      id: 'satellite_analysis',
      emoji: '🛰️',
      name: 'Satellite Analysis',
      agentClass: AgentClass.llm,
      blurb: 'Reports sourced chlorophyll-a observations and cross-source differences without HAB, catch, or safety inference.',
      accentColor: Color(0xFF38BDF8),
      defaultSources: <String>['ISRO MOSDAC OCM-3', 'NOAA CoastWatch', 'ESA OC-CCI'],
    ),
    AgentDescriptor(
      id: 'weather_hazard',
      emoji: '🌦️',
      name: 'Weather & Hazard',
      agentClass: AgentClass.llm,
      blurb: 'Checks Open-Meteo daily wind, gust, rain, and WMO weather-code outputs against ORCA policy thresholds.',
      accentColor: VerdictColors.caution,
      defaultSources: <String>['Open-Meteo Forecast'],
    ),
    AgentDescriptor(
      id: 'map_synoptic',
      emoji: '🗺️',
      name: 'Map Synoptic',
      agentClass: AgentClass.deterministic,
      blurb: 'Reports available backend GeoJSON overlays plus per-layer source and failure metadata; static port citations remain pending.',
      accentColor: Color(0xFF818CF8),
      defaultSources: <String>['ORCA GeoJSON layer service'],
    ),
    AgentDescriptor(
      id: 'marine_ecology',
      emoji: '🐟',
      name: 'Marine Ecology',
      agentClass: AgentClass.llm,
      blurb: 'Reports provisional SST, chlorophyll, and activity co-observations without making an ecological or catch verdict.',
      accentColor: Color(0xFF34D399),
      defaultSources: <String>['NOAA CoastWatch', 'MOSDAC OCM-3', 'INCOIS'],
    ),
    AgentDescriptor(
      id: 'fisheries_pfz',
      emoji: '🎣',
      name: 'Fisheries Context',
      agentClass: AgentClass.llm,
      blurb: 'Reports available environmental and GFW activity context without creating a PFZ or catch recommendation.',
      accentColor: Color(0xFFA78BFA),
      defaultSources: <String>['GFW AIS', 'ZoneSnapshot observations'],
    ),
    AgentDescriptor(
      id: 'anomaly_detection',
      emoji: '🔍',
      name: 'Anomaly Detection',
      agentClass: AgentClass.deterministic,
      blurb: 'Compares current values with a bounded recent Open-Meteo Archive baseline; reports unavailable when the archive cannot be fetched.',
      accentColor: Color(0xFFF472B6),
      defaultSources: <String>['Open-Meteo Archive'],
    ),
    AgentDescriptor(
      id: 'marine_risk',
      emoji: '🚨',
      name: 'Marine Risk',
      agentClass: AgentClass.deterministic,
      blurb: 'Deterministically combines available wave and weather hazard findings; missing physical evidence remains unknown.',
      accentColor: VerdictColors.noGo,
      defaultSources: <String>['All Agent Findings'],
    ),
    AgentDescriptor(
      id: 'orchestrator',
      emoji: '🧠',
      name: 'Orchestrator',
      agentClass: AgentClass.llm,
      blurb: 'Coordinates multi-agent waves, resolves dependencies, and synthesizes final skipper advice.',
      accentColor: Color(0xFFF59E0B),
      defaultSources: <String>['ORCA Situation Board'],
    ),
  ];

  /// Finds an agent by its unique ID. If unknown, returns generic fallback descriptor (§3).
  static AgentDescriptor findById(String id) {
    return all.firstWhere(
      (agent) => agent.id.toLowerCase() == id.toLowerCase(),
      orElse: () => AgentDescriptor(
        id: id,
        emoji: '🤖',
        name: _formatAgentName(id),
        agentClass: AgentClass.deterministic,
        blurb: 'Specialized backend agent contributing to ORCA analysis.',
        accentColor: VerdictColors.info,
      ),
    );
  }

  static String _formatAgentName(String id) {
    return id.split('_').map((w) => w.isEmpty ? '' : '${w[0].toUpperCase()}${w.substring(1)}').join(' ');
  }
}
