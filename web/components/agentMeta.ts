/** Shared eleven-stage display metadata — used by the Map-tab InsightPanel
 *  and the Advisory-tab agent board. One source of truth for names,
 *  emoji, and risk colours. */
export const AGENT_EMOJI: Record<string, string> = {
  ocean: "🌊",
  satellite: "🛰️",
  weather: "🌦️",
  gis: "🗺️",
  fisheries: "🎣",
  marine_ecology: "🐟",
  marine_risk: "🚨",
  anomaly: "📈",
  validation: "🔍",
  orca_reasoning: "🧠",
};

export const AGENT_LABEL: Record<string, { en: string; hi: string }> = {
  ocean: { en: "Ocean Analysis", hi: "समुद्र विश्लेषण" },
  satellite: { en: "Satellite Analysis", hi: "सैटेलाइट विश्लेषण" },
  weather: { en: "Weather", hi: "मौसम" },
  gis: { en: "GIS / Location", hi: "GIS / लोकेशन" },
  fisheries: { en: "Fisheries Context", hi: "मत्स्य संदर्भ" },
  marine_ecology: { en: "Marine Ecology", hi: "समुद्री पारिस्थितिकी" },
  marine_risk: { en: "Marine Risk", hi: "समुद्री जोखिम" },
  anomaly: { en: "Anomaly Detection", hi: "विसंगति जाँच" },
  validation: { en: "Data Validation", hi: "डेटा जाँच" },
  orca_reasoning: { en: "ORCA Reasoning", hi: "ORCA रीज़निंग" },
};

export const RISK_COLOR: Record<string, string> = {
  low: "bg-emerald-500/10 text-emerald-300 border-emerald-500/40",
  moderate: "bg-amber-500/10 text-amber-300 border-amber-500/40",
  high: "bg-orange-500/10 text-orange-300 border-orange-500/40",
  critical: "bg-red-500/10 text-red-300 border-red-500/40",
  unknown: "bg-slate-500/10 text-slate-300 border-slate-500/40",
};

export const RISK_DOT: Record<string, string> = {
  low: "🟢",
  moderate: "🟡",
  high: "🟠",
  critical: "🔴",
  unknown: "⚪",
};

export const SEVERITY_COLOR: Record<string, string> = {
  good: "text-emerald-300",
  info: "text-slate-400",
  warn: "text-amber-300",
  high: "text-orange-300",
  critical: "text-red-300",
  error: "text-red-300",
};
