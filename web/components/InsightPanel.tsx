"use client";

import { OrcaInsight } from "@/lib/orca-client";
import { t, Lang } from "@/lib/i18n";
import { AGENT_EMOJI, AGENT_LABEL, RISK_COLOR, RISK_DOT, SEVERITY_COLOR } from "@/components/agentMeta";

interface Props {
  insight: OrcaInsight | null;
  loading: boolean;
  zoneName: string;
  lang: Lang;
}

/** "NOAA ERDDAP: timeout after 12s" -> ["NOAA ERDDAP", "timeout after 12s"] */
function splitFailure(f: string): [string, string] {
  const i = f.indexOf(":");
  if (i === -1) return [f, ""];
  return [f.slice(0, i), f.slice(i + 1).trim()];
}

export default function InsightPanel({ insight, loading, zoneName, lang }: Props) {
  if (loading) {
    return (
      <div className="p-6 text-slate-300 space-y-3">
        <div className="animate-pulse text-base font-medium text-cyan-300">
          ⏳ {t(lang, "loading")}
        </div>
        <div className="text-sm text-slate-500 leading-relaxed">
          {t(lang, "panel_loading_hint")}
        </div>
      </div>
    );
  }
  if (!insight) {
    return (
      <div className="p-6 text-slate-500 text-sm leading-relaxed">
        👆 {t(lang, "panel_click_anywhere")}
      </div>
    );
  }

  const cov = insight.data_coverage;
  const coverageLimited = cov != null && cov.known < cov.total;
  // Agents WITH real measurements first; no-data agents sink to the bottom
  const agents = [...insight.agents].sort((a, b) => {
    const an = a.risk_level === "unknown" ? 1 : 0;
    const bn = b.risk_level === "unknown" ? 1 : 0;
    return an - bn;
  });

  return (
    <div className="p-5 space-y-4 overflow-y-auto h-full">
      <div>
        <h2 className="text-xl font-bold text-white leading-tight">{zoneName}</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          {insight.zone.lat.toFixed(2)}°, {insight.zone.lon.toFixed(2)}° · {insight.zone.date}
        </p>
      </div>

      {/* Overall risk */}
      <div className={`rounded-lg border px-4 py-3 ${RISK_COLOR[insight.overall_risk] || RISK_COLOR.unknown}`}>
        <div className="text-[11px] font-semibold uppercase tracking-wider opacity-70">
          {t(lang, "panel_overall_risk")}
        </div>
        <div className="text-2xl font-extrabold leading-snug">
          {RISK_DOT[insight.overall_risk] || ""} {insight.overall_risk.toUpperCase()}
        </div>
        {coverageLimited && (
          <div className="mt-1 text-xs opacity-80 leading-snug">
            {cov!.known}/{cov!.total} {t(lang, "panel_coverage")}
            {cov!.sources_failed > 0 ? ` · ${cov!.sources_failed} ${lang === "hi" ? "स्रोत बंद" : "source(s) down"}` : ""}
          </div>
        )}
      </div>

      {/* Recommendation */}
      <div className="rounded-lg border border-[#1C2A45] bg-[#0E1729] px-4 py-3">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-cyan-400/80 mb-1">
          {t(lang, "panel_recommendation")}
        </div>
        <div className="text-sm font-medium text-slate-100 leading-relaxed">
          {insight.recommendation}
        </div>
      </div>

      {/* Summary */}
      <div className="rounded-lg border border-[#1C2A45] bg-[#0B1322] px-4 py-3">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
          {t(lang, "panel_summary")}
        </div>
        <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-line">
          {insight.summary}
        </div>
      </div>

      {/* Data sources */}
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
          {t(lang, "panel_sources_used")}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {insight.data_sources_used.map((s) => (
            <span key={s} className="text-xs bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 px-2 py-1 rounded-md">
              ✓ {s}
            </span>
          ))}
        </div>
        {insight.data_sources_failed.length > 0 && (
          <details className="mt-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2">
            <summary className="cursor-pointer text-xs font-medium text-red-300">
              ⚠️ {insight.data_sources_failed.length} {t(lang, "panel_failed_n")}
            </summary>
            <ul className="mt-2 space-y-1.5">
              {insight.data_sources_failed.map((f) => {
                const [label, why] = splitFailure(f);
                return (
                  <li key={f} className="text-xs leading-relaxed">
                    <span className="font-semibold text-red-200">{label}</span>
                    {why && <span className="text-red-300/80"> — {why}</span>}
                  </li>
                );
              })}
            </ul>
          </details>
        )}
      </div>

      {/* Per-agent breakdown */}
      <div>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
          {t(lang, "panel_agents_n")} ({insight.agents.length})
        </div>
        <div className="space-y-2">
          {agents.map((a) => {
            const noData = a.risk_level === "unknown";
            const label = AGENT_LABEL[a.agent];
            return (
              <details
                key={a.agent}
                className={`rounded-lg border bg-[#0E1729] px-3 py-2 ${
                  noData ? "border-[#16233C] opacity-60" : "border-[#1C2A45]"
                }`}
              >
                <summary className="cursor-pointer flex items-center gap-2 list-none">
                  <span className="min-w-0 flex-1 text-sm font-medium text-slate-200 leading-snug break-words">
                    {AGENT_EMOJI[a.agent] || "•"} {label ? (lang === "hi" ? label.hi : label.en) : a.agent}
                  </span>
                  {noData ? (
                    <span className="shrink-0 text-[11px] px-2 py-0.5 rounded-md bg-[#131E35] text-slate-500 border border-[#1C2A45]">
                      {t(lang, "panel_no_data")}
                    </span>
                  ) : (
                    <span className={`shrink-0 text-[11px] px-2 py-0.5 rounded-md border ${RISK_COLOR[a.risk_level] || RISK_COLOR.unknown}`}>
                      {a.risk_level}
                    </span>
                  )}
                </summary>
                <div className="mt-2 text-xs text-slate-400 leading-relaxed">{a.summary}</div>
                {a.findings.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {a.findings.map((f, i) => (
                      <li key={i} className={`text-xs leading-relaxed ${SEVERITY_COLOR[f.severity] || ""}`}>
                        <span className="font-mono opacity-60">[{f.severity}]</span> {f.msg}
                      </li>
                    ))}
                  </ul>
                )}
              </details>
            );
          })}
        </div>
      </div>

      <div className="text-[11px] text-slate-600 pb-2">
        {t(lang, "panel_fetched")}: {new Date(insight.fetched_at).toLocaleString()}
      </div>
    </div>
  );
}
