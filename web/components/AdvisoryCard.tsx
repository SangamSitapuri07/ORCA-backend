"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Advisory, DemoZone, OrcaInsight, fetchAdvisory, fetchInsight, fmtLat, fmtLon } from "@/lib/orca-client";
import { t, Lang } from "@/lib/i18n";
import LineChart from "@/components/LineChart";
import { AGENT_EMOJI, AGENT_LABEL, RISK_COLOR, SEVERITY_COLOR } from "@/components/agentMeta";

const AdvisoryMap = dynamic(() => import("@/components/AdvisoryMap"), { ssr: false });
const FieldExplorer = dynamic(() => import("@/components/FieldExplorer"), { ssr: false });

const VERDICT_STYLE: Record<string, { bg: string; ring: string; label_en: string; label_hi: string }> = {
  go: { bg: "bg-green-600", ring: "ring-green-300", label_en: "GO", label_hi: "जा सकते हैं" },
  caution: { bg: "bg-amber-500", ring: "ring-amber-300", label_en: "CAUTION", label_hi: "सावधानी" },
  no_go: { bg: "bg-red-600", ring: "ring-red-300", label_en: "NO-GO", label_hi: "मत जाइए" },
  unknown: { bg: "bg-slate-600", ring: "ring-slate-300", label_en: "NOT VERIFIED", label_hi: "जाँच ज़रूरी" },
};

function Tile({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div className={`rounded-lg border p-3 bg-[#0E1729] ${warn ? "border-amber-500/60 shadow-[0_0_12px_#f59e0b22]" : "border-[#1C2A45]"}`}>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`text-lg font-bold ${warn ? "text-amber-300" : "text-slate-100"}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

export default function AdvisoryCard({
  zone,
  lang,
  advisory,
  setAdvisory,
  insight,
  insightLoading,
}: {
  zone: DemoZone;
  lang: Lang;
  advisory: Advisory | null;
  setAdvisory: (a: Advisory | null) => void;
  /** eleven-stage insight fetched for the Map tab — reused here when the
      coordinates match, so both tabs tell the same story. */
  insight?: OrcaInsight | null;
  insightLoading?: boolean;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [explorerOpen, setExplorerOpen] = useState(false);
  const [localInsight, setLocalInsight] = useState<OrcaInsight | null>(null);
  const [localInsightLoading, setLocalInsightLoading] = useState(false);
  const [localInsightErr, setLocalInsightErr] = useState<string | null>(null);

  const insightMatchesZone =
    insight &&
    Math.abs(insight.zone.lat - zone.lat) < 0.01 &&
    Math.abs(insight.zone.lon - zone.lon) < 0.01;
  const effInsight = insightMatchesZone ? insight : localInsight;
  const agentsBusy = (insightMatchesZone ? insightLoading : localInsightLoading) ?? false;

  const loadAgents = async () => {
    setLocalInsightLoading(true);
    setLocalInsightErr(null);
    try {
      setLocalInsight(await fetchInsight(zone.lat, zone.lon));
    } catch (e) {
      setLocalInsightErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLocalInsightLoading(false);
    }
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const a = await fetchAdvisory(zone.lat, zone.lon);
      setAdvisory(a);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLocalInsight(null);
    setLocalInsightErr(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zone.lat, zone.lon]);

  if (loading && !advisory) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400 bg-[#070D1A]">
        <div className="text-center">
          <div className="text-3xl mb-2 animate-bounce">🌊</div>
          <p className="text-sm text-slate-300">{t(lang, "loading")}</p>
          <p className="text-xs mt-1 text-slate-500">11 analysis stages · deterministic safety verdict</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-[#070D1A]">
        <div className="text-center max-w-sm">
          <div className="text-3xl mb-2">🔌</div>
          <p className="text-sm text-slate-400 mb-3">{error}</p>
          <button onClick={load} className="bg-cyan-600 hover:bg-cyan-500 text-white rounded px-4 py-2 text-sm">
            {t(lang, "refresh")}
          </button>
        </div>
      </div>
    );
  }

  if (!advisory) return null;

  const v = advisory.variables;
  const st = VERDICT_STYLE[advisory.verdict] ?? VERDICT_STYLE.caution;
  const sw = advisory.safe_window;

  return (
    <div className="h-full overflow-y-auto bg-[#070D1A] p-4 space-y-4">
      {/* verdict banner: icon + shape + colour (readable by anyone) */}
      <div className={`rounded-xl ${st.bg} text-white p-5 shadow-lg ring-4 ${st.ring}`}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-4xl font-black flex items-center gap-3">
              <span>{advisory.icon}</span>
              <span>{lang === "hi" ? st.label_hi : st.label_en}</span>
            </div>
            <p className="mt-1 text-sm opacity-95">
              {lang === "hi" ? advisory.headline_hi : advisory.headline_en}
            </p>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="bg-white/20 hover:bg-white/30 rounded px-3 py-2 text-sm disabled:opacity-50"
          >
            {loading ? "…" : t(lang, "refresh")}
          </button>
        </div>
        <div className="mt-2 text-xs opacity-80">
          {t(lang, "advisory_for")} {zone.name} ({fmtLat(zone.lat)}, {fmtLon(zone.lon)}) ·{" "}
          {t(lang, "valid_until")} {advisory.valid_until.slice(11, 16)} UTC
        </div>
      </div>

      {/* plain-language card — the one block a non-technical reader needs */}
      {(advisory.plain_en?.length || advisory.plain_hi?.length) ? (
        <div className="rounded-lg border border-cyan-500/25 bg-cyan-500/5 p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-cyan-300/90 mb-1.5">
            🗣️ {lang === "hi" ? "सीधी-सादी भाषा में" : "In plain words"}
          </div>
          <div className="space-y-1">
            {(lang === "hi" ? advisory.plain_hi : advisory.plain_en)?.map((line, i) => (
              <p key={i} className={`text-sm leading-relaxed ${i === 0 ? "font-semibold text-slate-100" : "text-slate-300"}`}>
                {line}
              </p>
            ))}
          </div>
        </div>
      ) : null}

      {/* 48 h evidence charts — the EXACT arrays the verdict rules read,
          drawn with real axes so a flat line at 1.6 m still tells a story */}
      {advisory.hourly_chart && advisory.hourly_chart.labels.length > 1 && (() => {
        const hc = advisory.hourly_chart;
        const has = (a?: (number | null)[] | null) => !!a && a.some((v) => v != null);
        const ChartCard = ({ title, children, hint }: { title: string; children: React.ReactNode; hint?: string }) => (
          <div className="rounded-lg border border-[#1C2A45] bg-[#0B1322] p-3">
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">{title}</div>
            {children}
            {hint && <div className="text-[9px] text-slate-600 mt-0.5 leading-snug">{hint}</div>}
          </div>
        );
        return (
          <div className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-3">
            <div className="flex items-center justify-between mb-2 flex-wrap gap-1">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-cyan-300/90">
                📈 {lang === "hi" ? "अगले 48 घंटे — घंटे-दर-घंटे, असली मॉडल डेटा" : "Next 48 h — hour by hour, real model data"}
              </div>
              <div className="text-[9px] text-slate-600">Open-Meteo · ECMWF / MeteoFrance · UTC</div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <ChartCard
                title={`🌊 ${lang === "hi" ? "लहरें + swell" : "Waves + swell"}`}
                hint={lang === "hi" ? "2.5 m से ऊपर छोटी नाव के लिए मुश्किल · 4 m = खतरनाक" : "2.5 m+ rough for small boats · 4 m = unsafe"}>
                <LineChart
                  labels={hc.labels} unit=" m"
                  series={[
                    { label: lang === "hi" ? "लहरें" : "waves", values: hc.wave_m, color: "#22d3ee" },
                    ...(has(hc.swell_m) ? [{ label: "swell", values: hc.swell_m!, color: "#818cf8", dashed: true }] : []),
                  ]}
                  thresholds={[
                    { value: 2.5, color: "#f59e0b", label: "2.5 caution" },
                    { value: 4, color: "#ef4444", label: "4 unsafe" },
                  ]}
                />
              </ChartCard>
              <ChartCard
                title={`💨 ${lang === "hi" ? "हवा + झोंके (gusts)" : "Wind + gusts"}`}
                hint={lang === "hi" ? "20 kn = तेज़ हवा · 34 kn = तूफ़ान चेतावनी (gale)" : "20 kn = strong breeze · 34 kn = gale warning"}>
                <LineChart
                  labels={hc.labels} unit=" kn"
                  series={[
                    { label: lang === "hi" ? "हवा" : "wind", values: hc.wind_kn, color: "#a78bfa" },
                    { label: "gusts", values: hc.gust_kn, color: "#f472b6", dashed: true },
                  ]}
                  thresholds={[
                    { value: 20, color: "#f59e0b", label: "20 caution" },
                    { value: 34, color: "#ef4444", label: "34 gale" },
                  ]}
                />
              </ChartCard>
              {has(hc.current_kn) && (
                <ChartCard
                  title={`🌀 ${lang === "hi" ? "समुद्री धारा (current)" : "Surface current"}`}
                  hint={lang === "hi" ? "0.5-2.5 kn आम · 3 kn+ बहुत तेज़ — ज़ाल डालते समय ध्यान" : "0.5-2.5 kn typical · 3 kn+ very strong — mind your drift sets"}>
                  <LineChart
                    labels={hc.labels} unit=" kn"
                    series={[{ label: "current", values: hc.current_kn!, color: "#34d399" }]}
                    thresholds={[{ value: 3, color: "#f59e0b", label: "3 strong" }]}
                  />
                </ChartCard>
              )}
              {has(hc.sst_c) && (
                <ChartCard
                  title={`🌡️ ${lang === "hi" ? "समुद्र का तापमान (SST)" : "Sea surface temp (SST)"}`}
                  hint={lang === "hi" ? "marine-model SST · मछली आमतौर पर 26-29°C बैंड पसंद करती है" : "marine-model SST · baitfish usually like the 26-29°C band"}>
                  <LineChart
                    labels={hc.labels} unit="°C"
                    series={[{ label: "SST", values: hc.sst_c!, color: "#fbbf24" }]}
                  />
                </ChartCard>
              )}
            </div>
          </div>
        );
      })()}

      {/* mini location map — where am I, which way is the PFZ */}
      <AdvisoryMap
        lat={zone.lat}
        lon={zone.lon}
        pfzNm={v.nearest_pfz_nm}
        pfzBearing={v.nearest_pfz_bearing}
        lang={lang}
      />

      {/* visual explorer — one button opens the full sampled map */}
      <button
        onClick={() => setExplorerOpen(true)}
        className="w-full rounded-lg border border-emerald-500/30 bg-emerald-500/5 hover:bg-emerald-500/10 text-emerald-300 font-semibold text-sm py-3 transition"
      >
        🔬 {lang === "hi"
          ? "विज़ुअल एक्सप्लोरर खोलें — मछली-स्पॉट, लहरें, हवा नक्शे पर"
          : "Open Visual Explorer — fish spots, waves & wind on a real map"}
      </button>
      {explorerOpen && (
        <FieldExplorer
          lat={zone.lat}
          lon={zone.lon}
          lang={lang}
          trend={advisory.hourly_chart ?? null}
          onClose={() => setExplorerOpen(false)}
        />
      )}

      {/* variable tiles — every number is live */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        <Tile label={`🌊 ${t(lang, "waves")} (${t(lang, "now")})`} value={v.wave_height_m != null ? `${v.wave_height_m} m` : "—"} warn={(v.wave_height_m ?? 0) >= 2.5} sub={`${t(lang, "peak_48h")}: ${advisory.outlook_48h?.wave_max_m ?? "—"} m · ${t(lang, "swell")}: ${v.swell_m ?? "—"} m`} />
        <Tile label={`💨 ${t(lang, "wind")} (${t(lang, "now")})`} value={v.wind_kts != null ? `${Math.round(v.wind_kts)} kn` : "—"} sub={`${t(lang, "gusts")}: ${v.gust_kts != null ? Math.round(v.gust_kts) : "—"} kn · ${t(lang, "peak_48h")}: ${advisory.outlook_48h?.gust_max_kn != null ? Math.round(advisory.outlook_48h.gust_max_kn) : "—"} kn`} warn={(v.gust_kts ?? 0) >= 28} />
        <Tile label={`🌡️ ${t(lang, "sst")}`} value={v.sst_c != null ? `${v.sst_c.toFixed(1)} °C` : "—"}
          sub={v.sst_source ? (v.sst_source.includes("marine model") ? "marine model (hourly)" : "daily SST record") : undefined} />
        <Tile label={`🌀 ${t(lang, "current")}`} value={v.current_kn != null ? `${v.current_kn} kn` : "—"} sub={v.current_dir ?? undefined} />
        <Tile label={`🛰️ ${t(lang, "chlorophyll")}`} value={v.chlorophyll_mg_m3 != null ? `${v.chlorophyll_mg_m3.toFixed(2)} mg/m³` : "—"} sub={v.pfz_advisory_date ? `PFZ: ${v.pfz_advisory_date}` : undefined} />
        <Tile label={`🎣 ${t(lang, "nearest_pfz")}`} value={v.nearest_pfz_nm != null ? `${v.nearest_pfz_nm} NM` : "—"} sub={v.nearest_pfz_bearing ? `${v.nearest_pfz_bearing} · INCOIS` : "none nearby today"} />
        <Tile label={`⚠️ ${t(lang, "cyclone")}`} value={v.cyclone_dist_km != null ? `${v.cyclone_dist_km} km` : "✓ clear"} warn={v.cyclone_dist_km != null && v.cyclone_dist_km < 800} />
      </div>

      {/* safe window */}
      <div className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4">
        <h3 className="text-sm font-semibold text-slate-200 mb-1">⏱️ {t(lang, "safe_window")}</h3>
        {sw.found ? (
          <p className="text-sm text-slate-300">
            <span className="font-mono font-semibold text-cyan-300">{sw.from_utc?.slice(5, 16).replace("T", " ")}</span>
            {" → "}
            <span className="font-mono font-semibold text-cyan-300">{sw.to_utc?.slice(5, 16).replace("T", " ")}</span> UTC
            <span className="ml-2 text-xs bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 rounded px-2 py-0.5">{sw.hours} h</span>
          </p>
        ) : (
          <p className="text-sm text-slate-500">{t(lang, "no_safe_window")} {sw.note ? `(${sw.note})` : ""}</p>
        )}
      </div>

      {/* reasons */}
      <div className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4">
        <h3 className="text-sm font-semibold text-slate-200 mb-2">🔎 {t(lang, "reasons")}</h3>
        <ul className="space-y-1.5">
          {advisory.reasons.map((r, i) => (
            <li key={i} className="text-sm flex gap-2">
              <span className={
                r.severity === "no_go" ? "text-red-400" :
                r.severity === "caution" ? "text-amber-400" : "text-slate-500"
              }>
                {r.severity === "no_go" ? "⛔" : r.severity === "caution" ? "⚠️" : "ℹ️"}
              </span>
              <span className="text-slate-300">{r.msg}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* eleven-stage board — the full multi-agent analysis, same insight the
          Map-tab panel uses. Every agent's verdict + findings in one place. */}
      <div className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4">
        <div className="flex items-center justify-between mb-2 flex-wrap gap-1">
          <h3 className="text-sm font-semibold text-slate-200">
            🧠 {lang === "hi" ? "11 चरणों की पूरी राय" : "Full eleven-stage breakdown"}
          </h3>
          {effInsight && (
            <span className={`text-[10px] px-2 py-0.5 rounded-md border ${RISK_COLOR[effInsight.overall_risk] || RISK_COLOR.unknown}`}>
              {lang === "hi" ? "कुल जोखिम" : "overall"}: {effInsight.overall_risk.toUpperCase()}
            </span>
          )}
        </div>
        {effInsight ? (
          <>
            {effInsight.recommendation && (
              <p className="text-xs text-cyan-200/90 bg-cyan-500/5 border border-cyan-500/20 rounded-md px-3 py-2 mb-2 leading-relaxed">
                💡 {effInsight.recommendation}
              </p>
            )}
            <div className="space-y-1.5">
              {[...effInsight.agents]
                .sort((a, b) => (a.risk_level === "unknown" ? 1 : 0) - (b.risk_level === "unknown" ? 1 : 0))
                .map((a) => {
                  const noData = a.risk_level === "unknown";
                  const label = AGENT_LABEL[a.agent];
                  return (
                    <details key={a.agent}
                      className={`rounded-md border px-3 py-2 bg-[#0B1322] ${noData ? "border-[#16233C] opacity-65" : "border-[#1C2A45]"}`}>
                      <summary className="cursor-pointer flex items-center gap-2 list-none">
                        <span className="text-sm">{AGENT_EMOJI[a.agent] || "•"}</span>
                        <span className="min-w-0 flex-1 text-xs font-medium text-slate-200 leading-snug break-words">
                          {label ? (lang === "hi" ? label.hi : label.en) : a.agent}
                        </span>
                        <span className={`shrink-0 text-[10px] px-2 py-0.5 rounded-md border ${RISK_COLOR[a.risk_level] || RISK_COLOR.unknown}`}>
                          {noData ? (lang === "hi" ? "डेटा नहीं" : "no data") : a.risk_level}
                        </span>
                      </summary>
                      <div className="mt-1.5 text-[11px] text-slate-400 leading-relaxed">{a.summary}</div>
                      {a.findings.length > 0 && (
                        <ul className="mt-1.5 space-y-1">
                          {a.findings.map((f, i) => (
                            <li key={i} className={`text-[11px] leading-relaxed ${SEVERITY_COLOR[f.severity] || ""}`}>
                              <span className="font-mono opacity-60">[{f.severity}]</span> {f.msg}
                            </li>
                          ))}
                        </ul>
                      )}
                    </details>
                  );
                })}
            </div>
            <div className="mt-2 text-[10px] text-slate-600">
              {lang === "hi" ? "एजेंट विश्लेषण समय" : "agents ran"}: {new Date(effInsight.fetched_at).toLocaleString()}
            </div>
          </>
        ) : (
          <div className="text-xs text-slate-500 space-y-2">
            <p>
              {agentsBusy
                ? (lang === "hi" ? "⏳ 11 चरण लाइव डेटा पर काम कर रहे हैं… (10-30 सेकंड)" : "⏳ 11 analysis stages working on live data… (10-30 s)")
                : (lang === "hi"
                    ? "Map tab पर point click करने से यहाँ अपने-आप आ जाता है — या अभी चलाएँ:"
                    : "Click a point on the Map tab and it appears here automatically — or run it now:")}
            </p>
            {!agentsBusy && (
              <button onClick={loadAgents}
                className="rounded-md border border-cyan-500/40 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 text-xs font-semibold px-3 py-2 transition">
                🧠 {lang === "hi" ? "11-चरण analysis अभी लोड करें" : "Load the eleven-stage analysis now"}
              </button>
            )}
            {localInsightErr && <p className="text-red-400/80">⚠️ {localInsightErr}</p>}
          </div>
        )}
      </div>

      {/* sources footer — full transparency */}
      <div className="rounded-lg border border-[#1C2A45] bg-[#0E1729] p-4 text-xs text-slate-500 space-y-1">
        <div><span className="font-semibold text-slate-400">{t(lang, "sources")}:</span> {advisory.sources.join(" · ")}</div>
        {advisory.sources_failed.length > 0 && (
          <div><span className="font-semibold text-slate-400">{t(lang, "failed_sources")}:</span> {advisory.sources_failed.join(" · ")}</div>
        )}
        <div className="italic">{advisory.disclaimer}</div>
        <div>{t(lang, "cyclone")}: {v.cyclone_note}</div>
      </div>
    </div>
  );
}
