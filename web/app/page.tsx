"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  Advisory,
  DEFAULT_ZONE,
  DemoZone,
  INDIAN_COASTAL_ZONES,
  OrcaAlert,
  OrcaInsight,
  fetchHealth,
  fetchInsight,
} from "@/lib/orca-client";
import { t, Lang } from "@/lib/i18n";
import InsightPanel from "@/components/InsightPanel";
import AskOrca from "@/components/AskOrca";
import AdvisoryCard from "@/components/AdvisoryCard";
import AlertsPanel from "@/components/AlertsPanel";
import SettingsPanel from "@/components/SettingsPanel";
import {
  IconMap,
  IconChat,
  IconShield,
  IconBell,
  IconSettings,
  IconWave,
} from "@/components/icons";

// react-leaflet uses window/document — client-only
const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

type Tab = "map" | "ask" | "advisory" | "alerts" | "settings";

/** Header chips show the REAL backend-reported source status — nothing cosmetic */
const SRC_LABEL: Record<string, string> = {
  mosdac: "MOSDAC",
  noaa_erddap: "NOAA",
  esa_occci: "OC-CCI",
  openmeteo: "Open-Meteo",
  gfw: "GFW",
  incois_pfz_wfs: "INCOIS PFZ",
  incois_las: "INCOIS",
  jtwc: "JTWC",
};
const SRC_ORDER = ["mosdac", "noaa_erddap", "esa_occci", "openmeteo", "gfw", "incois_pfz_wfs", "incois_las", "jtwc"];

function SourceChips() {
  const [sources, setSources] = useState<Record<string, string> | null>(null);
  const [commit, setCommit] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const pull = () => {
      fetchHealth()
        .then((h) => { if (alive) { setSources(h.data_sources ?? {}); setCommit(h.build_commit ?? null); } })
        .catch(() => { if (alive) setSources(null); });
    };
    pull();
    const id = setInterval(pull, 60_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  if (sources === null) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full bg-red-500/10 border border-red-500/30 text-red-300">
        <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
        backend down
      </span>
    );
  }
  const keys = SRC_ORDER.filter((k) => k in sources);
  return (
    <div className="flex items-center gap-1.5 flex-wrap justify-end">
      {keys.map((k, i) => {
        const v = String(sources[k]);
        const live = v.toLowerCase().includes("live");
        return (
          <span
            key={k}
            title={v}
            className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full border ${
              live
                ? "bg-emerald-400/10 border-emerald-400/25 text-emerald-300"
                : "bg-amber-400/10 border-amber-400/25 text-amber-300"
            } ${i > 3 ? "hidden lg:inline-flex" : i > 1 ? "hidden sm:inline-flex" : ""}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-400 chip-dot" : "bg-amber-400"}`} />
            {SRC_LABEL[k] ?? k}
          </span>
        );
      })}
      {/* build stamp — every screenshot now proves WHICH checkout the
          backend is running ("purana code chal raha tha" loop-killer) */}
      {commit && (
        <span
          title={`backend build commit: ${commit} — pull + backend restart ke baad yahan latest hash dikhna chahiye`}
          className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-1 rounded-full border border-slate-600/40 text-slate-500"
        >
          ⎇ {commit}
        </span>
      )}
    </div>
  );
}

export default function Home() {
  const [tab, setTab] = useState<Tab>("map");
  const [lang, setLang] = useState<Lang>("hi");
  const [zone, setZone] = useState<DemoZone>(DEFAULT_ZONE);
  const [insight, setInsight] = useState<OrcaInsight | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [advisory, setAdvisory] = useState<Advisory | null>(null);
  const [ticker, setTicker] = useState<OrcaAlert[]>([]);

  const insightBusyRef = useRef(false);
  const pendingZoneRef = useRef<DemoZone | null>(null);
  const runIdRef = useRef(0);
  // One silent auto-retry after a 504: the backend's timeout reply keeps
  // computing in the background and lands in cache — asking again a few
  // seconds later usually returns the full eleven-stage board with no second
  // click from the user ("1 button ke andar").
  const autoRetriedKeyRef = useRef<string | null>(null);
  const retryPendingForRunRef = useRef(0);

  // Latest click WINS: rapid clicks queue up and only the newest zone
  // gets analyzed next — no dropped clicks, no parallel agent-chains
  // strangling the network.
  const handleSelectZone = (z: DemoZone) => {
    autoRetriedKeyRef.current = null; // a fresh click re-arms the auto-retry
    pendingZoneRef.current = z;
    setZone(z);
    setAdvisory(null); // stale until re-fetched
    setInsight(null);
    setInsightLoading(true);
    if (insightBusyRef.current) return; // runNext() picks it up when free
    runNextInsight();
  };

  const runNextInsight = () => {
    const z = pendingZoneRef.current;
    if (!z) return;
    pendingZoneRef.current = null;
    insightBusyRef.current = true;
    const myId = ++runIdRef.current;
    fetchInsight(z.lat, z.lon)
      .then((r) => { if (runIdRef.current === myId) setInsight(r); })
      .catch((err) => {
        if (runIdRef.current !== myId) return; // superseded by a newer click
        const timedOut =
          err instanceof Error &&
          (err.name === "TimeoutError" || /timed out/i.test(err.message) || /API 504/.test(err.message));
        const zoneKey = `${z.lat.toFixed(2)},${z.lon.toFixed(2)}`;
        if (timedOut && autoRetriedKeyRef.current !== zoneKey) {
          // Silent retry ONCE — the background compute has had ~9 s to
          // finish and fill the caches, so this call is usually instant.
          autoRetriedKeyRef.current = zoneKey;
          retryPendingForRunRef.current = myId;
          window.setTimeout(() => {
            if (runIdRef.current !== myId || pendingZoneRef.current) return; // superseded
            retryPendingForRunRef.current = 0;
            pendingZoneRef.current = z;
            runNextInsight();
          }, 9000);
          return; // spinner stays on; the honest card only shows if the retry also fails
        }
        setInsight({
          zone: { lat: z.lat, lon: z.lon, date: new Date().toISOString().slice(0, 10) },
          agents: [],
          overall_risk: "unknown",
          summary: timedOut
            ? (lang === "hi"
                ? "नेटवर्क धीमा है और विश्लेषण समय से पहले पूरा नहीं हुआ। कुछ सेकंड बाद उसी बिंदु पर दोबारा क्लिक करें — कैश होने से दूसरी बार तेज़ चलेगा।"
                : "Slow network — the analysis didn't finish in time. Click the same point again in a few seconds; caches make the retry much faster.")
            : (lang === "hi"
                ? `ORCA API तक नहीं पहुँच पाए। ${err instanceof Error ? err.message : String(err)}`
                : `Failed to reach the ORCA API. ${err instanceof Error ? err.message : String(err)}`),
          recommendation: timedOut
            ? (lang === "hi" ? "दोबारा प्रयास करें — backend ज़िंदा है, बस धीमा है।" : "Retry — the backend is alive, just slow.")
            : (lang === "hi" ? "जाँचें कि configured ORCA Box backend पर चल रहा है।" : "Check that the FastAPI backend is running on port 8000."),
          data_sources_used: [],
          data_sources_failed: [timedOut ? "Network: analysis timed out (retry warms the cache)" : "API: backend unreachable"],
          fetched_at: new Date().toISOString(),
        });
      })
      .finally(() => {
        insightBusyRef.current = false;
        if (pendingZoneRef.current) {
          runNextInsight(); // a newer click was queued while we worked
        } else if (runIdRef.current === myId && retryPendingForRunRef.current !== myId) {
          setInsightLoading(false); // stays ON while the silent retry is pending
        }
      });
  };

  const TABS: { id: Tab; label: string; icon: (cls: string) => ReactNode }[] = [
    { id: "map", label: t(lang, "tab_map"), icon: (c) => <IconMap size={19} className={c} /> },
    { id: "ask", label: t(lang, "tab_ask"), icon: (c) => <IconChat size={19} className={c} /> },
    { id: "advisory", label: t(lang, "tab_advisory"), icon: (c) => <IconShield size={19} className={c} /> },
    { id: "alerts", label: t(lang, "tab_alerts"), icon: (c) => <IconBell size={19} className={c} /> },
    { id: "settings", label: t(lang, "tab_settings"), icon: (c) => <IconSettings size={19} className={c} /> },
  ];

  return (
    <div className="h-screen flex overflow-hidden bg-[#070D1A] text-[#DBE4F3]">
      {/* left icon rail */}
      <aside className="w-[60px] sm:w-[64px] shrink-0 flex flex-col items-center gap-1 py-4 bg-[#0A1120] border-r border-[#16233C]">
        <div
          className="mb-3 h-9 w-9 rounded-xl bg-gradient-to-br from-cyan-500/25 to-blue-600/25 border border-cyan-400/30 flex items-center justify-center text-cyan-300"
          title="ORCA"
        >
          <IconWave size={20} />
        </div>
        {TABS.map(({ id, label, icon }) => {
          const active = tab === id;
          return (
            <button
              key={id}
              onClick={() => setTab(id)}
              title={label}
              className={`relative w-11 sm:w-12 flex flex-col items-center gap-1 py-2.5 rounded-xl transition-all duration-150 ${
                active
                  ? "bg-cyan-400/10 text-cyan-300"
                  : "text-[#4D5D80] hover:bg-white/[0.04] hover:text-[#9FB0D1]"
              }`}
            >
              {active && <span className="absolute left-0 top-1/2 -translate-y-1/2 h-6 w-[3px] rounded-r-full bg-cyan-400" />}
              {icon("")}
              <span className="text-[9px] font-medium leading-none tracking-wide">{label}</span>
            </button>
          );
        })}
        {/* (B10) Voyage Planner lab — route/navigation flow polished here
            FIRST, then port ho kar Android app mein wapas aayega */}
        <Link
          href="/navigate"
          title="Voyage Planner — route testing lab"
          className="w-11 sm:w-12 flex flex-col items-center gap-1 py-2.5 rounded-xl transition-all duration-150 text-[#4D5D80] hover:bg-white/[0.04] hover:text-[#9FB0D1]"
        >
          <span className="text-[19px] leading-none">🧭</span>
          <span className="text-[9px] font-medium leading-none tracking-wide">voyage</span>
        </Link>
        {/* (B18) Live Beacon — "Samudri Rakshak Net": anonymous ping +
            SOS rescue web lab; baaqi tabs ke saath independent page */}
        <Link
          href="/live"
          title="Live Beacon — SOS rescue net"
          className="w-11 sm:w-12 flex flex-col items-center gap-1 py-2.5 rounded-xl transition-all duration-150 text-[#4D5D80] hover:bg-white/[0.04] hover:text-[#9FB0D1]"
        >
          <span className="text-[19px] leading-none">📡</span>
          <span className="text-[9px] font-medium leading-none tracking-wide">rescue</span>
        </Link>
        <div className="mt-auto pb-1 text-[8px] font-medium tracking-[0.2em] text-[#34446A] [writing-mode:vertical-rl] rotate-180 select-none">
          SIH 2026 · PS 176
        </div>
      </aside>

      {/* main column */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* header */}
        <header className="shrink-0 bg-[#0A1120]/95 border-b border-[#16233C] px-4 sm:px-5 h-14 flex items-center justify-between gap-3">
          <div className="min-w-0 flex items-baseline gap-2.5">
            <h1 className="text-[17px] font-bold tracking-tight text-white leading-none">
              ORCA
            </h1>
            <span className="text-[11px] text-cyan-300/80 font-medium hidden sm:inline">Marine Intelligence</span>
            <span className="text-[10px] text-[#4D5D80] truncate hidden md:inline">· {t(lang, "app_tagline")}</span>
          </div>
          <SourceChips />
        </header>

        {/* alert ticker — any active warning scrolls by */}
        {ticker.length > 0 && (
          <div className="shrink-0 bg-red-500/10 border-b border-red-500/25 text-red-300 text-xs px-4 py-1.5 flex items-center gap-3 overflow-hidden">
            <span className="font-semibold animate-pulse shrink-0">{t(lang, "ticker_prefix")}</span>
            <div className="whitespace-nowrap overflow-hidden text-ellipsis">
              {ticker.map((a) => `${a.simulated ? "[DEMO] " : ""}${lang === "hi" ? a.title_hi : a.title_en} (till ${a.valid_until.slice(11, 16)} UTC)`).join("  ·  ")}
            </div>
          </div>
        )}

        {/* tab content — Map tab keeps its own layout (map component untouched) */}
        <div className="flex-1 overflow-hidden" hidden={tab !== "map"}>
          <div className="h-full grid grid-cols-1 md:grid-cols-[2fr_1fr]">
            <div className="relative">
              <MapView zones={INDIAN_COASTAL_ZONES} selected={zone} onSelect={handleSelectZone} lang={lang} />
              <div className="absolute bottom-4 left-4 surface-2 backdrop-blur shadow-xl px-3.5 py-2.5 text-xs max-w-xs z-[1000]">
                <div className="font-semibold text-white mb-0.5">
                  {zone.name}
                </div>
                <div className="text-[#7D8DB0]">
                  {t(lang, "map_click_hint")}
                </div>
              </div>
            </div>
            <div className="bg-[#0A1120] border-l border-[#16233C] overflow-hidden">
              <InsightPanel insight={insight} loading={insightLoading} zoneName={zone.name} lang={lang} />
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-hidden" hidden={tab !== "ask"}>
          <AskOrca zone={zone} lang={lang} onVerdict={setAdvisory} />
        </div>

        <div className="flex-1 overflow-hidden" hidden={tab !== "advisory"}>
          <AdvisoryCard zone={zone} lang={lang} advisory={advisory} setAdvisory={setAdvisory}
            insight={insight} insightLoading={insightLoading} />
        </div>

        <div className="flex-1 overflow-hidden" hidden={tab !== "alerts"}>
          <AlertsPanel zone={zone} lang={lang} ticker={ticker} setTicker={setTicker} />
        </div>

        <div className="flex-1 overflow-hidden" hidden={tab !== "settings"}>
          <SettingsPanel zone={zone} setZone={setZone} lang={lang} setLang={setLang} />
        </div>
      </div>
    </div>
  );
}
