"use client";

/** 🧭 ORCA Voyage Planner — TEST LAB (web-first, B10)
 *
 *  The FULL navigate flow, tested on the big screen before it goes back
 *  to the Android app:
 *
 *    Q1  intent  — 🎣 "tell ME where to fish" (voyage AI) ·
 *                  ⚓ "I have a destination" (manual route check)
 *    Q2  start   — GPS / typed coords / click on map
 *    Q3  go      — voyage recommendations (score-auditable) OR
 *                  manual destination (typed / map click / harbour list)
 *
 *  then the route chain: /route-check (land verify) → /route-advisory
 *  (per-point live marine weather, worst-case verdict). Every number on
 *  screen came straight from the backend — nothing invented, every
 *  source failure shown. That honesty IS the product. */

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  PointState,
  RouteAdvisory,
  RouteCheckResponse,
  VoyageReco,
  VoyageResponse,
  fetchHealth,
  fetchRouteAdvisory,
  fetchRouteCheck,
  fetchVoyage,
  fmtLat,
  fmtLon,
} from "@/lib/orca-client";
import { HARBOURS } from "@/lib/harbours";

// react-leaflet needs window — client-only
const RouteMap = dynamic(() => import("@/components/RouteMap"), { ssr: false });

type LL = { lat: number; lon: number };
type Intent = "fish" | "route" | null;
type PickMode = "start" | "dest" | null;

const COMPASS = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
];
const compass = (deg: number) => COMPASS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];

const STATE_STYLE: Record<PointState, { dot: string; label: string; text: string }> = {
  good: { dot: "#16a34a", label: "GOOD", text: "text-emerald-300" },
  caution: { dot: "#d97706", label: "CAUTION", text: "text-amber-300" },
  danger: { dot: "#dc2626", label: "DANGER", text: "text-red-300" },
  unknown: { dot: "#64748b", label: "UNKNOWN", text: "text-slate-400" },
};

/** Accepts "19.03, 72.83" / "19.03 72.83" — honest parse errors, no guessing. */
function parseLL(txt: string): LL | string {
  const parts = txt
    .replace(/[°NSEW]/gi, "")
    .split(/[\s,]+/)
    .filter(Boolean)
    .map(Number);
  if (parts.length !== 2) return "format: lat, lon (e.g. 19.03, 72.83)";
  const [lat, lon] = parts;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return "not numbers — check the values";
  if (lat < -90 || lat > 90) return "latitude must be between −90 and 90";
  if (lon < -180 || lon > 180) return "longitude must be between −180 and 180";
  return { lat, lon };
}

const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Truth-first knots display: 1 decimal so a raw 19.6 kn NEVER masquerades
    as "20" sitting next to the ≥20 kn rule line — every cell must be
    auditable against the printed thresholds (judge-proofing, B10a). */
const fmtKn = (v: number) => {
  const r = Math.round(v * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
};

// demo presets = REAL ocean coords (integration test values we already
// ran against the live backend — Mumbai→SW 55 NM came back GO 5/5)
const ROUTE_PRESETS: { label: string; s: LL; d: LL }[] = [
  { label: "Mumbai → SW 55 NM", s: { lat: 19.03, lon: 72.83 }, d: { lat: 18.56, lon: 72.0 } },
  { label: "Veraval → offshore", s: { lat: 20.9, lon: 70.37 }, d: { lat: 20.42, lon: 69.95 } },
  { label: "Chennai → offshore", s: { lat: 13.08, lon: 80.29 }, d: { lat: 13.0, lon: 80.9 } },
];
const VOYAGE_PRESETS: { label: string; s: LL }[] = [
  { label: "Mumbai offshore", s: { lat: 19.03, lon: 72.83 } },
  { label: "Okha / Gujarat", s: { lat: 22.47, lon: 69.07 } },
  { label: "Cochin offshore", s: { lat: 9.93, lon: 76.26 } },
];

export default function NavigateLab() {
  // ── wizard state ──
  const [intent, setIntent] = useState<Intent>(null);
  const [start, setStart] = useState<LL | null>(null);
  const [dest, setDest] = useState<LL | null>(null);
  const [startTxt, setStartTxt] = useState("");
  const [destTxt, setDestTxt] = useState("");
  const [pick, setPick] = useState<PickMode>(null);
  const [gpsBusy, setGpsBusy] = useState(false);
  const [startErr, setStartErr] = useState<string | null>(null);
  const [destErr, setDestErr] = useState<string | null>(null);
  const [radiusKm, setRadiusKm] = useState(120);

  // ── results ──
  const [rc, setRc] = useState<RouteCheckResponse | null>(null);
  const [rcErr, setRcErr] = useState<string | null>(null);
  const [rcBusy, setRcBusy] = useState(false);
  const [ra, setRa] = useState<RouteAdvisory | null>(null);
  const [raErr, setRaErr] = useState<string | null>(null);
  const [raBusy, setRaBusy] = useState(false);
  const [voy, setVoy] = useState<VoyageResponse | null>(null);
  const [voyErr, setVoyErr] = useState<string | null>(null);
  const [voyBusy, setVoyBusy] = useState(false);

  // health pill
  const [backendUp, setBackendUp] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    const pull = () =>
      fetchHealth()
        .then(() => alive && setBackendUp(true))
        .catch(() => alive && setBackendUp(false));
    pull();
    const id = setInterval(pull, 60_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // ── helpers ─────────────────────────────────────────────────────

  /** Route results are tied to (start,dest) — when either changes, old
      analysis is STALE: clear it (never show yesterday's verdict for
      today's coordinates). */
  const invalidateRoute = () => {
    setRc(null);
    setRcErr(null);
    setRa(null);
    setRaErr(null);
  };

  const applyStart = (ll: LL) => {
    setStart(ll);
    setStartTxt(`${ll.lat.toFixed(4)}, ${ll.lon.toFixed(4)}`);
    setStartErr(null);
    invalidateRoute();
    setVoy(null); // voyage recommendations belong to the OLD start point
    setVoyErr(null);
  };

  const applyDest = (ll: LL) => {
    setDest(ll);
    setDestTxt(`${ll.lat.toFixed(4)}, ${ll.lon.toFixed(4)}`);
    setDestErr(null);
    invalidateRoute();
  };

  const onMapPick = (lat: number, lon: number) => {
    if (pick === "start") applyStart({ lat, lon });
    else if (pick === "dest") applyDest({ lat, lon });
    setPick(null);
  };

  const useGps = () => {
    if (!navigator.geolocation) {
      setStartErr("this browser has no geolocation API");
      return;
    }
    setGpsBusy(true);
    setStartErr(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGpsBusy(false);
        applyStart({ lat: pos.coords.latitude, lon: pos.coords.longitude });
      },
      (e) => {
        setGpsBusy(false);
        setStartErr(`GPS failed: ${e.message} — type coords or pick on map`);
      },
      { enableHighAccuracy: true, timeout: 12_000, maximumAge: 30_000 }
    );
  };

  /** The route chain: land verify (fast) → per-point weather advisory
      (slow, live). Errors surface honestly per stage with a retry. */
  const runRoute = async (s: LL, d: LL) => {
    if (s.lat === d.lat && s.lon === d.lon) {
      setRaErr("start and destination are the same point");
      return;
    }
    invalidateRoute();
    setRcBusy(true);
    try {
      setRc(await fetchRouteCheck(s.lat, s.lon, d.lat, d.lon));
    } catch (e) {
      setRcErr(errMsg(e));
    } finally {
      setRcBusy(false);
    }
    setRaBusy(true);
    try {
      setRa(await fetchRouteAdvisory(s.lat, s.lon, d.lat, d.lon));
    } catch (e) {
      setRaErr(errMsg(e));
    } finally {
      setRaBusy(false);
    }
  };

  const runVoyage = async () => {
    if (!start) return;
    setVoy(null);
    setVoyErr(null);
    setVoyBusy(true);
    try {
      setVoy(await fetchVoyage(start.lat, start.lon, radiusKm));
    } catch (e) {
      setVoyErr(errMsg(e));
    } finally {
      setVoyBusy(false);
    }
  };

  const setCourse = (reco: VoyageReco) => {
    const d = { lat: reco.lat, lon: reco.lon };
    applyDest(d);
    if (start) void runRoute(start, d);
  };

  const legs: [number, number][] | null =
    ra?.legs?.length ? ra.legs : rc?.legs?.length ? rc.legs : null;

  // ── tiny presentational bits ────────────────────────────────────

  const StatChip = ({ label, value }: { label: string; value: string }) => (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-[#0E1729] border border-[#1C2A45] px-2 py-1 text-[11px]">
      <span className="text-[#4D5D80]">{label}</span>
      <span className="font-bold text-white">{value}</span>
    </span>
  );

  const StatePill = ({ state }: { state: PointState }) => {
    const s = STATE_STYLE[state] ?? STATE_STYLE.unknown;
    return (
      <span className={`inline-flex items-center gap-1 text-[10px] font-bold ${s.text}`}>
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.dot }} />
        {s.label}
      </span>
    );
  };

  const Panel = ({ step, title, children }: { step: string; title: string; children: React.ReactNode }) => (
    <div className="rounded-xl border border-[#16233C] bg-[#0A1120] p-3.5">
      <div className="flex items-baseline gap-2 mb-2.5">
        <span className="text-[10px] font-bold tracking-widest text-cyan-400">{step}</span>
        <h2 className="text-[13px] font-bold text-white">{title}</h2>
      </div>
      {children}
    </div>
  );

  const ErrCard = ({ msg, onRetry }: { msg: string; onRetry?: () => void }) => (
    <div className="mt-2 rounded-lg border border-red-500/35 bg-red-500/10 p-2.5">
      <div className="text-[11px] text-red-300 font-medium break-words">{msg}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1.5 text-[11px] font-bold text-red-200 underline underline-offset-2 hover:text-red-100"
        >
          ↻ retry
        </button>
      )}
    </div>
  );

  // ── render ──────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#070D1A] text-[#DBE4F3] flex flex-col">
      {/* header */}
      <header className="shrink-0 bg-[#0A1120]/95 border-b border-[#16233C] px-4 h-14 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href="/"
            className="text-[12px] font-semibold text-[#9FB0D1] hover:text-cyan-300 transition-colors"
          >
            ← dashboard
          </Link>
          <span className="text-[#16233C]">|</span>
          <h1 className="text-[15px] font-bold tracking-tight text-white truncate">
            🧭 Voyage Planner <span className="text-[10px] align-middle font-bold tracking-widest text-amber-300 border border-amber-400/40 rounded px-1.5 py-0.5 ml-1">TEST LAB</span>
          </h1>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full border ${
            backendUp === null
              ? "bg-slate-500/10 border-slate-500/30 text-slate-300"
              : backendUp
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                : "bg-red-500/10 border-red-500/30 text-red-300"
          }`}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{
              background: backendUp === null ? "#94a3b8" : backendUp ? "#34d399" : "#f87171",
            }}
          />
          {backendUp === null ? "checking backend…" : backendUp ? "backend live" : "backend DOWN — start uvicorn"}
        </span>
      </header>

      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[400px,minmax(0,1fr)] gap-4 p-4">
        {/* ─── left: wizard ─── */}
        <section className="space-y-3 min-w-0">
          <div className="rounded-lg border border-cyan-400/25 bg-cyan-400/5 p-2.5 text-[11px] leading-relaxed text-cyan-200/90">
            Pehle yahin polish + test karte hain 📋 — Android app ka Navigate tab abhi
            <b> hidden</b> hai (B10). Flow final hone ke baad wapas phone mein aayega.
            Sab numbers <b>live backend</b> se aate hain — koi dummy nahi.
          </div>

          {/* Q1 — intent */}
          <Panel step="STEP 1" title="Kya karna hai aaj?">
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setIntent("fish")}
                className={`rounded-lg border p-3 text-left transition-all ${
                  intent === "fish"
                    ? "border-cyan-400/60 bg-cyan-400/10"
                    : "border-[#1C2A45] bg-[#0E1729] hover:border-[#2A3C60]"
                }`}
              >
                <div className="text-[20px]">🎣</div>
                <div className="text-[12px] font-bold text-white mt-1">Machli kahan milegi?</div>
                <div className="text-[10px] text-[#4D5D80] mt-0.5">
                  Official PFZ lines analyze kare — weather evidence ke saath
                </div>
              </button>
              <button
                onClick={() => setIntent("route")}
                className={`rounded-lg border p-3 text-left transition-all ${
                  intent === "route"
                    ? "border-cyan-400/60 bg-cyan-400/10"
                    : "border-[#1C2A45] bg-[#0E1729] hover:border-[#2A3C60]"
                }`}
              >
                <div className="text-[20px]">⚓</div>
                <div className="text-[12px] font-bold text-white mt-1">Route check karo</div>
                <div className="text-[10px] text-[#4D5D80] mt-0.5">
                  Mujhe jagah pata hai — wahan tak ka verdict
                </div>
              </button>
            </div>
          </Panel>

          {/* Q2 — start */}
          <Panel step="STEP 2" title="Kahan se shuru?">
            <div className="flex gap-2 mb-2">
              <button
                onClick={useGps}
                disabled={gpsBusy}
                className="flex-1 rounded-lg border border-[#1C2A45] bg-[#0E1729] hover:border-cyan-400/40 px-2.5 py-2 text-[11px] font-bold text-[#DBE4F3] disabled:opacity-50 transition-all"
              >
                {gpsBusy ? "⏳ GPS…" : "📍 Use my GPS"}
              </button>
              <button
                onClick={() => setPick(pick === "start" ? null : "start")}
                className={`flex-1 rounded-lg border px-2.5 py-2 text-[11px] font-bold transition-all ${
                  pick === "start"
                    ? "border-cyan-400/60 bg-cyan-400/10 text-cyan-200"
                    : "border-[#1C2A45] bg-[#0E1729] text-[#DBE4F3] hover:border-cyan-400/40"
                }`}
              >
                {pick === "start" ? "🗺 map pe click karo…" : "🗺 Pick on map"}
              </button>
            </div>
            <div className="flex gap-2">
              <input
                value={startTxt}
                onChange={(e) => setStartTxt(e.target.value)}
                placeholder="lat, lon — e.g. 19.03, 72.83"
                className="min-w-0 flex-1 rounded-lg border border-[#1C2A45] bg-[#070D1A] px-2.5 py-2 text-[12px] font-mono text-white placeholder:text-[#34446A] focus:outline-none focus:border-cyan-400/50"
              />
              <button
                onClick={() => {
                  const r = parseLL(startTxt);
                  if (typeof r === "string") setStartErr(r);
                  else applyStart(r);
                }}
                className="rounded-lg bg-cyan-500/15 border border-cyan-400/40 px-3 py-2 text-[11px] font-bold text-cyan-200 hover:bg-cyan-500/25 transition-all"
              >
                Set
              </button>
            </div>
            {startErr && <ErrCard msg={startErr} />}
            {start && (
              <div className="mt-2 flex items-center gap-2">
                <StatChip label="START" value={`${fmtLat(start.lat)} ${fmtLon(start.lon)}`} />
                <button
                  onClick={() => {
                    setStart(null);
                    setStartTxt("");
                    invalidateRoute();
                    setVoy(null);
                  }}
                  className="text-[10px] font-bold text-[#4D5D80] hover:text-red-300"
                >
                  ✕ clear
                </button>
              </div>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="text-[10px] text-[#34446A] self-center">coast presets:</span>
              {VOYAGE_PRESETS.map((p) => (
                <button
                  key={p.label}
                  onClick={() => applyStart(p.s)}
                  className="rounded-md border border-[#1C2A45] bg-[#0E1729] px-2 py-1 text-[10px] text-[#9FB0D1] hover:border-cyan-400/40 hover:text-cyan-200 transition-all"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </Panel>

          {/* Q3 — intent dependent */}
          {intent === "fish" && (
            <Panel step="STEP 3" title="🤖 AI batao — kahan jaun?">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[11px] text-[#4D5D80]">range</span>
                <input
                  type="number"
                  min={20}
                  max={400}
                  value={radiusKm}
                  onChange={(e) => setRadiusKm(Math.max(20, Math.min(400, Number(e.target.value) || 120)))}
                  className="w-20 rounded-lg border border-[#1C2A45] bg-[#070D1A] px-2 py-1.5 text-[12px] font-mono text-white focus:outline-none focus:border-cyan-400/50"
                />
                <span className="text-[11px] text-[#4D5D80]">km</span>
                {[120, 200, 300].map((r) => (
                  <button
                    key={r}
                    onClick={() => setRadiusKm(r)}
                    className={`rounded-md px-2 py-1 text-[10px] font-bold border transition-all ${
                      radiusKm === r
                        ? "border-cyan-400/60 bg-cyan-400/10 text-cyan-200"
                        : "border-[#1C2A45] text-[#4D5D80] hover:text-[#9FB0D1]"
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
              <button
                onClick={runVoyage}
                disabled={!start || voyBusy}
                className="w-full rounded-lg bg-cyan-500/20 border border-cyan-400/50 px-3 py-2.5 text-[13px] font-bold text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                {voyBusy
                  ? "⏳ analyze ho raha hai… (20–40 s — PFZ + chl + weather)"
                  : start
                    ? "🤖 TU analyze kar — kahan jaun?"
                    : "⬆ pehle STEP 2 — start point set karo"}
              </button>
              {voyErr && <ErrCard msg={voyErr} onRetry={runVoyage} />}
              {voy && !voy.found && (
                <div className="mt-2 rounded-lg border border-amber-400/30 bg-amber-400/10 p-2.5 text-[11px] text-amber-200">
                  <b>Koi recommendation nahi mili</b> — ye jhooth nahi bolta:
                  {(voy.notes ?? []).map((n, i) => (
                    <div key={i} className="mt-1 text-[10.5px] text-amber-200/80">• {n}</div>
                  ))}
                </div>
              )}
              {voy?.found && (
                <div className="mt-2.5 space-y-2">
                  <div className="flex flex-wrap gap-1.5">
                    <StatChip label="evaluated" value={String(voy.candidates_evaluated ?? "—")} />
                    <StatChip label="range" value={`${voy.max_km} km`} />
                    <StatChip label="at" value={(voy.analyzed_at ?? "").replace("T", " ").replace("+00:00", "Z").slice(0, 19)} />
                  </div>
                  {(voy.notes ?? []).length > 0 && (
                    <div className="rounded-lg border border-amber-400/25 bg-amber-400/5 p-2">
                      <div className="text-[10px] font-bold text-amber-300 mb-0.5">⚠ honest source notes (kuch sources fail ho sakte hain — yahan sab dikhata hoon):</div>
                      {(voy.notes ?? []).map((n, i) => (
                        <div key={i} className="text-[10.5px] text-amber-200/80">• {n}</div>
                      ))}
                    </div>
                  )}
                  {voy.recommendations.map((r, i) => (
                    <div
                      key={i}
                      className="rounded-xl border border-[#1C2A45] bg-[#0E1729] p-3 hover:border-[#2A3C60] transition-all"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="shrink-0 h-6 w-6 rounded-md bg-[#1C2A45] flex items-center justify-center text-[11px] font-bold text-cyan-300">
                            {i + 1}
                          </span>
                          <span
                            className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold tracking-wide ${
                              r.kind === "pfz"
                                ? "bg-teal-500/15 text-teal-300 border border-teal-500/40"
                                : "bg-violet-500/15 text-violet-300 border border-violet-500/40"
                            }`}
                          >
                            {r.kind === "pfz" ? "OFFICIAL PFZ ✔" : "CHL HOTSPOT"}
                          </span>
                          <span className="truncate text-[12px] font-bold text-white">{r.name}</span>
                        </div>
                        <span className="shrink-0 rounded-lg bg-cyan-400/15 border border-cyan-400/40 px-2 py-0.5 text-[12px] font-bold text-cyan-200">
                          {r.score}
                          {r.score_base != null && r.score_base !== r.score && (
                            <span className="ml-1 text-[9px] font-semibold text-[#7d8db3] line-through">{r.score_base}</span>
                          )}
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#9FB0D1]">
                        <span>🧭 {r.distance_nm.toFixed(1)} NM · {compass(r.bearing_deg)} ({r.bearing_deg.toFixed(0)}°)</span>
                        {r.wave_m != null && <span>🌊 {r.wave_m.toFixed(1)} m</span>}
                        {r.wind_kn != null && <span>💨 {r.wind_kn.toFixed(0)} kn</span>}
                        {r.sst_c != null && <span>🌡 {r.sst_c.toFixed(1)} °C</span>}
                        {r.chl != null && <span>🦠 chl {r.chl.toFixed(1)} mg/m³</span>}
                        <StatePill state={r.state} />
                        {r.crowd && (
                          <span
                            className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${
                              r.crowd.level === "low"
                                ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                                : r.crowd.level === "moderate"
                                ? "bg-amber-500/15 text-amber-300 border-amber-500/40"
                                : r.crowd.level === "high"
                                ? "bg-rose-500/15 text-rose-300 border-rose-500/40"
                                : "bg-slate-500/15 text-slate-300 border-slate-500/40"
                            }`}
                            title="Crowd-spread (B14): ORCA community picks (24 h, anonymous 0.25° cells) + GFW AIS fleet hours (30 d)"
                          >
                            👥 {r.crowd.level === "high" ? "bheed ZYADA" : r.crowd.level === "moderate" ? "bheed madhyam" : r.crowd.level === "low" ? "bheed kam" : "bheed ?"}
                            {r.crowd.gfw_hours_30d != null && ` · 🚢 ${r.crowd.gfw_hours_30d}h/30d`}
                            {r.crowd.community_recent > 0 && ` · ${r.crowd.community_recent} ORCA pick${r.crowd.community_recent > 1 ? "s" : ""}/24h`}
                          </span>
                        )}
                      </div>
                      {r.why && <div className="mt-1 text-[10.5px] italic text-amber-200/80">{r.why}</div>}
                      {r.crowd?.note && <div className="mt-0.5 text-[10px] text-slate-400">🚢 {r.crowd.note}</div>}
                      <details className="mt-1.5 group">
                        <summary className="cursor-pointer text-[10.5px] font-bold text-[#4D5D80] group-open:text-cyan-300 hover:text-cyan-200">
                          score ka breakdown ▸ (auditable — har +/− ka reason)
                        </summary>
                        <ul className="mt-1 space-y-0.5">
                          {r.reasons.map((rs, j) => (
                            <li key={j} className="text-[10.5px] text-[#9FB0D1]">· {rs}</li>
                          ))}
                        </ul>
                        {voy.scoring && (
                          <div className="mt-1 text-[9.5px] text-[#34446A]">{voy.scoring}</div>
                        )}
                      </details>
                      <button
                        onClick={() => setCourse(r)}
                        disabled={raBusy || rcBusy}
                        className="mt-2 w-full rounded-lg bg-teal-500/20 border border-teal-400/50 px-3 py-2 text-[12px] font-bold text-teal-100 hover:bg-teal-500/30 disabled:opacity-40 transition-all"
                      >
                        ⛵ Set course here → full route analysis
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          )}

          {intent === "route" && (
            <Panel step="STEP 3" title="Destination kahan hai?">
              <div className="flex gap-2 mb-2">
                <button
                  onClick={() => setPick(pick === "dest" ? null : "dest")}
                  className={`flex-1 rounded-lg border px-2.5 py-2 text-[11px] font-bold transition-all ${
                    pick === "dest"
                      ? "border-pink-400/60 bg-pink-400/10 text-pink-200"
                      : "border-[#1C2A45] bg-[#0E1729] text-[#DBE4F3] hover:border-pink-400/40"
                  }`}
                >
                  {pick === "dest" ? "🗺 map pe click karo…" : "🗺 Pick on map"}
                </button>
                <select
                  defaultValue=""
                  onChange={(e) => {
                    const h = HARBOURS.find((x) => x.name === e.target.value);
                    if (h) applyDest({ lat: h.lat, lon: h.lon });
                  }}
                  className="flex-1 rounded-lg border border-[#1C2A45] bg-[#0E1729] px-2 py-2 text-[11px] text-[#DBE4F3] focus:outline-none focus:border-cyan-400/50"
                >
                  <option value="" disabled>
                    ⚓ harbour se choose…
                  </option>
                  {HARBOURS.map((h) => (
                    <option key={h.name} value={h.name}>
                      {h.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex gap-2">
                <input
                  value={destTxt}
                  onChange={(e) => setDestTxt(e.target.value)}
                  placeholder="lat, lon — e.g. 18.56, 72.00"
                  className="min-w-0 flex-1 rounded-lg border border-[#1C2A45] bg-[#070D1A] px-2.5 py-2 text-[12px] font-mono text-white placeholder:text-[#34446A] focus:outline-none focus:border-pink-400/50"
                />
                <button
                  onClick={() => {
                    const r = parseLL(destTxt);
                    if (typeof r === "string") setDestErr(r);
                    else applyDest(r);
                  }}
                  className="rounded-lg bg-pink-500/15 border border-pink-400/40 px-3 py-2 text-[11px] font-bold text-pink-200 hover:bg-pink-500/25 transition-all"
                >
                  Set
                </button>
              </div>
              {destErr && <ErrCard msg={destErr} />}
              {dest && (
                <div className="mt-2 flex items-center gap-2">
                  <StatChip label="DEST" value={`${fmtLat(dest.lat)} ${fmtLon(dest.lon)}`} />
                  <button
                    onClick={() => {
                      setDest(null);
                      setDestTxt("");
                      invalidateRoute();
                    }}
                    className="text-[10px] font-bold text-[#4D5D80] hover:text-red-300"
                  >
                    ✕ clear
                  </button>
                </div>
              )}
              <button
                onClick={() => start && dest && void runRoute(start, dest)}
                disabled={!start || !dest || rcBusy || raBusy}
                className="mt-2.5 w-full rounded-lg bg-cyan-500/20 border border-cyan-400/50 px-3 py-2.5 text-[13px] font-bold text-cyan-100 hover:bg-cyan-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                {rcBusy || raBusy
                  ? "⏳ analysis chal rahi hai… (15–60 s — live weather per point)"
                  : !start || !dest
                    ? "start + destination dono set karo"
                    : "🔍 FULL route analysis — land + weather + verdict"}
              </button>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="text-[10px] text-[#34446A] self-center">route presets:</span>
                {ROUTE_PRESETS.map((p) => (
                  <button
                    key={p.label}
                    onClick={() => {
                      applyStart(p.s);
                      applyDest(p.d);
                      void runRoute(p.s, p.d);
                    }}
                    className="rounded-md border border-[#1C2A45] bg-[#0E1729] px-2 py-1 text-[10px] text-[#9FB0D1] hover:border-cyan-400/40 hover:text-cyan-200 transition-all"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </Panel>
          )}

          {intent === null && (
            <Panel step="STEP 3" title="…">
              <div className="text-[11.5px] text-[#4D5D80]">
                ⬆ STEP 1 mein intent choose karo — fishing ya route check.
              </div>
            </Panel>
          )}
        </section>

        {/* ─── right: map + analysis ─── */}
        <section className="min-w-0 space-y-3">
          <div className="h-[420px] rounded-xl overflow-hidden border border-[#16233C]">
            <RouteMap
              start={start}
              dest={dest}
              legs={legs}
              points={ra?.points ?? []}
              recos={voy?.recommendations ?? []}
              pickArmed={pick !== null}
              onPick={onMapPick}
            />
          </div>

          {/* map legend */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-[#4D5D80]">
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-teal-500" /> S start</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-pink-600" /> D destination</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-500" /> - - direct line (land pe atki = blocked)</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-sky-400" /> verified sea path (GLOBE)</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full border border-white bg-sky-300" /> waypoint</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-600" /> good point</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-600" /> caution</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-600" /> danger</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-slate-500" /> unknown</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-teal-400" /> voyage PFZ</span>
            <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-violet-500" /> official PFZ candidate</span>
          </div>

          {/* route-check (land) banner */}
          {(rcBusy || rc || rcErr) && (
            <div
              className={`rounded-xl border p-3 ${
                rcBusy
                  ? "border-[#1C2A45] bg-[#0A1120]"
                  : rcErr
                    ? "border-red-500/35 bg-red-500/10"
                    : rc?.rerouted && rc?.ok === true
                      ? "border-cyan-400/40 bg-cyan-400/10"
                      : rc?.ok === true
                        ? "border-emerald-500/35 bg-emerald-500/10"
                        : rc?.ok === false
                          ? "border-red-500/40 bg-red-500/10"
                          : "border-slate-500/35 bg-slate-500/10"
              }`}
            >
              {rcBusy && <div className="text-[12px] text-[#9FB0D1]">⏳ land verify chal raha hai (GLOBE 1 km mask, course sample ho raha)…</div>}
              {rcErr && <div className="text-[12px] text-red-300">route-check failed: {rcErr}</div>}
              {rc && (
                <div className="text-[12px]">
                  {rc.rerouted && rc.ok === true ? (
                    <>
                      <b className="text-cyan-300">
                        🌊 SEA PATH computed — direct course LAND tha, paani se reroute ho gaya
                        ({(rc.waypoints?.length ?? Math.max(0, rc.legs.length - 2))} waypoints ·
                        SRI LANKA / coast ke around · har leg 1 km pe re-verified ✅)
                      </b>
                      {rc.land_hit && (
                        <div className="mt-1 text-[11px] text-cyan-100/80">
                          direct line land pe atki thi {fmtLat(rc.land_hit.lat)} {fmtLon(rc.land_hit.lon)} pe
                          ({(rc.land_hit.sail_km / 1.852).toFixed(1)} NM out) — isliye samundar se ghumaya
                        </div>
                      )}
                    </>
                  ) : (
                    <b className={rc.ok === true ? "text-emerald-300" : rc.ok === false ? "text-red-300" : "text-slate-300"}>
                      {rc.ok === true
                        ? "✅ Course SARA PANI — GLOBE 1 km land mask ne verify kiya"
                        : rc.ok === false
                          ? "❌ Course LAND mein atak raha hai aur koi verified paani ka raasta nahi mila"
                          : "❔ Land verify HUA NAHI (mask unavailable) — route ko careful treat karo"}
                    </b>
                  )}
                  {!rc.rerouted && rc.detour && <span className="ml-2 text-[11px] text-sky-300">(detour waypoint add hua — real computed)</span>}
                  {rc.rerouted !== true && rc.land_hit && (
                    <div className="mt-1 text-[11px] text-red-200/85">
                      land at {fmtLat(rc.land_hit.lat)} {fmtLon(rc.land_hit.lon)} · after {(rc.land_hit.sail_km / 1.852).toFixed(1)} NM
                    </div>
                  )}
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {rc.straight_distance_km != null && (
                      <StatChip label="direct (blocked)" value={`${(rc.straight_distance_km / 1.852).toFixed(1)} NM`} />
                    )}
                    <StatChip label={rc.rerouted ? "sea path" : "distance"} value={`${(rc.distance_km / 1.852).toFixed(1)} NM (${rc.distance_km.toFixed(0)} km)`} />
                    {rc.straight_distance_km != null && (
                      <StatChip label="extra sail" value={`+${((rc.distance_km - rc.straight_distance_km) / 1.852).toFixed(1)} NM`} />
                    )}
                    <StatChip label="bearing" value={`${compass(rc.bearing_deg)} ${rc.bearing_deg.toFixed(0)}°`} />
                    <StatChip label="legs" value={String(rc.legs.length)} />
                    <StatChip label="native check" value={`${rc.sample_step_km} km`} />
                  </div>
                </div>
              )}
            </div>
          )}

          {(raErr || raBusy) && (
            <div className={`rounded-xl border p-3 ${raErr ? "border-red-500/35 bg-red-500/10" : "border-[#1C2A45] bg-[#0A1120]"}`}>
              {raBusy && (
                <div className="text-[12px] text-[#9FB0D1]">
                  ⏳ route-advisory: har ~30 km point pe LIVE marine forecast fetch ho rahi (15–60 s) —
                  coffee lo ☕, evidence ban raha hai…
                </div>
              )}
              {raErr && <ErrCard msg={`route-advisory: ${raErr}`} onRetry={() => start && dest && void runRoute(start, dest)} />}
            </div>
          )}

          {/* route-advisory = THE analysis */}
          {ra && (
            <div className="space-y-3">
              {/* verdict banner */}
              <div
                className={`rounded-xl border p-4 ${
                  ra.verdict.level === "go"
                    ? "border-emerald-500/40 bg-emerald-500/10"
                    : ra.verdict.level === "caution"
                      ? "border-amber-500/40 bg-amber-500/10"
                      : ra.verdict.level === "nogo"
                        ? "border-red-500/45 bg-red-500/10"
                        : "border-slate-500/35 bg-slate-500/10"
                }`}
              >
                <div
                  className={`text-[19px] font-extrabold ${
                    ra.verdict.level === "go"
                      ? "text-emerald-300"
                      : ra.verdict.level === "caution"
                        ? "text-amber-300"
                        : ra.verdict.level === "nogo"
                          ? "text-red-300"
                          : "text-slate-300"
                  }`}
                >
                  {ra.verdict.level === "go" && "✅ GO — course safe hai (sab points clear)"}
                  {ra.verdict.level === "caution" && "⚠️ CAUTION — savdhani se jao (kuch points borderline)"}
                  {ra.verdict.level === "nogo" && "🚫 NO-GO — aaj mat niklo (danger point / land block)"}
                  {ra.verdict.level === "unknown" && "❔ UNKNOWN — data kaafi nahi hai, verify hua bhi nahi; risky"}
                </div>
                <div className="mt-1 text-[11px] text-[#9FB0D1]">
                  Worst-point rule: sabse bura point hi verdict decide karta hai — average kabhi nahi
                  (average danger ko chhupa deta hai).
                </div>
                {(() => {
                  // KYUN saamne hona chahiye — NO-GO land se ya weather se,
                  // aur KAUNSA point decide kiya (B12: verdict ambiguity killed)
                  const pts = ra.points ?? [];
                  const danger = pts.find((p) => p.state === "danger");
                  const caution = pts.find((p) => p.state === "caution");
                  const unknowns = pts.filter((p) => p.state === "unknown").length;
                  let line: string | null = null;
                  if (ra.verdict.land_verified === false) {
                    line = "🎯 kyun: course hi LAND se atka hua hai (destination tak paani ka raasta nahi)";
                  } else if (danger) {
                    line = `🎯 kyun: point ${pts.indexOf(danger) + 1} — ${danger.why ?? danger.note ?? "danger"}`;
                  } else if (caution && ra.verdict.level === "caution") {
                    line = `🎯 kyun: point ${pts.indexOf(caution) + 1} — ${caution.why ?? caution.note ?? "caution"}`;
                  } else if (unknowns > 0 && ra.verdict.level === "caution") {
                    line = `🎯 kyun: ${unknowns} point(s) ne data nahi diya → unknown = savdhani (kabhi blind-GO nahi)`;
                  }
                  if (!line) return null;
                  return (
                    <div className="mt-1 text-[12px] font-bold text-white">
                      {line}
                      {danger && unknowns > 0 && (
                        <span className="ml-2 text-[11px] font-medium text-[#9FB0D1]">
                          · +{unknowns} unknown (reason table+sources mein — chhupaya nahi)
                        </span>
                      )}
                    </div>
                  );
                })()}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <StatChip label="points known" value={`${ra.verdict.points_known}/${ra.verdict.points_total}`} />
                  <StatChip
                    label="land verified"
                    value={
                      ra.verdict.land_verified === true
                        ? "yes (GLOBE)"
                        : ra.verdict.land_verified === false
                          ? "BLOCKED"
                          : "NOT verified"
                    }
                  />
                  {ra.straight_distance_nm != null && (
                    <StatChip label="direct (blocked)" value={`${ra.straight_distance_nm.toFixed(1)} NM`} />
                  )}
                  <StatChip label={ra.rerouted ? "sea path" : "distance"} value={`${ra.distance_nm.toFixed(1)} NM`} />
                  <StatChip label="bearing" value={`${compass(ra.bearing_deg)} ${ra.bearing_deg.toFixed(0)}°`} />
                  {ra.rerouted && (
                    <StatChip label="route" value={`sea-path · ${ra.waypoints?.length ?? "?"} waypoints`} />
                  )}
                  {!ra.rerouted && ra.detour && <StatChip label="route" value="has detour waypoint" />}
                </div>
                {ra.safe_window_at_start && (
                  <div className="mt-2 rounded-lg border border-[#1C2A45] bg-[#0E1729] p-2 text-[11px] text-[#9FB0D1]">
                    🕐 <b className="text-white">Safest departure window (start point):</b>{" "}
                    {ra.safe_window_at_start.found
                      ? `${ra.safe_window_at_start.from_utc ?? "?"} → ${ra.safe_window_at_start.to_utc ?? "?"} (${ra.safe_window_at_start.hours ?? "?"} h calm stretch)`
                      : (ra.safe_window_at_start.note ?? "agle 48 ghanton mein ≥3 h ki calm window nahi mili — ye bhi sach hai")}
                  </div>
                )}
              </div>

              {/* EVIDENCE table — kya dekh kar decide hua */}
              <div className="rounded-xl border border-[#16233C] bg-[#0A1120] p-3.5">
                <h3 className="text-[13px] font-bold text-white mb-1">
                  🔬 Evidence — har sampled point ke REAL numbers
                </h3>
                <div className="text-[10.5px] text-[#4D5D80] mb-2">
                  course ko ~{ra.sample_spacing_km ?? 30} km pe sample kiya; har point pe live Open-Meteo marine + forecast; yahi values verdict banati hain.
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-[11px] border-collapse min-w-[760px]">
                    <thead>
                      <tr className="text-left text-[#4D5D80] border-b border-[#16233C]">
                        <th className="py-1.5 pr-2 font-semibold">#</th>
                        <th className="py-1.5 pr-2 font-semibold">position</th>
                        <th className="py-1.5 pr-2 font-semibold">sailed</th>
                        <th className="py-1.5 pr-2 font-semibold">state</th>
                        <th className="py-1.5 pr-2 font-semibold">wave m</th>
                        <th className="py-1.5 pr-2 font-semibold">wave 48h↗</th>
                        <th className="py-1.5 pr-2 font-semibold">wind kn</th>
                        <th className="py-1.5 pr-2 font-semibold">wind 48h↗</th>
                        <th className="py-1.5 pr-2 font-semibold">gust 48h↗</th>
                        <th className="py-1.5 pr-2 font-semibold">cur kn</th>
                        <th className="py-1.5 pr-2 font-semibold">SST °C</th>
                        <th className="py-1.5 font-semibold">reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ra.points.map((p, i) => {
                        const st = STATE_STYLE[p.state] ?? STATE_STYLE.unknown;
                        return (
                          <tr key={i} className="border-b border-[#101C33] align-top">
                            <td className="py-1.5 pr-2 font-bold text-white">
                              {i + 1}
                              {p.vertex ? " ★" : ""}
                            </td>
                            <td className="py-1.5 pr-2 font-mono text-[#9FB0D1]">
                              {p.lat.toFixed(3)},{p.lon.toFixed(3)}
                            </td>
                            <td className="py-1.5 pr-2 text-[#9FB0D1]">{(p.sail_km / 1.852).toFixed(1)} NM</td>
                            <td className="py-1.5 pr-2">
                              <span className={`inline-flex items-center gap-1 font-bold ${st.text}`}>
                                <span className="h-1.5 w-1.5 rounded-full" style={{ background: st.dot }} />
                                {st.label}
                              </span>
                            </td>
                            <td className="py-1.5 pr-2 text-[#DBE4F3]">{p.wave_m != null ? p.wave_m.toFixed(1) : "—"}</td>
                            <td className="py-1.5 pr-2 text-[#DBE4F3]">{p.wave_48h_max_m != null ? p.wave_48h_max_m.toFixed(1) : "—"}</td>
                            <td className="py-1.5 pr-2 text-[#DBE4F3]">{p.wind_kn != null ? fmtKn(p.wind_kn) : "—"}</td>
                            <td className="py-1.5 pr-2 text-[#DBE4F3]">{p.wind_48h_max_kn != null ? fmtKn(p.wind_48h_max_kn) : "—"}</td>
                            <td className="py-1.5 pr-2 text-[#DBE4F3]">{p.gust_48h_max_kn != null ? fmtKn(p.gust_48h_max_kn) : "—"}</td>
                            <td className="py-1.5 pr-2 text-[#DBE4F3]">{p.current_kn != null ? p.current_kn.toFixed(2) : "—"}</td>
                            <td className="py-1.5 pr-2 text-[#DBE4F3]">{p.sst_c != null ? p.sst_c.toFixed(1) : "—"}</td>
                            <td className="py-1.5 text-amber-200/80 italic">{p.why ?? p.note ?? ""}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="mt-1.5 text-[9.5px] text-[#34446A]">
                  ★ = route vertex (start/end/detour corner) · &ldquo;—&rdquo; = source ne value nahi di (honest null, hamesha &ldquo;—&rdquo; hi dikhega, koi banaya hua number nahi)
                </div>
              </div>

              {/* rules + method cards */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                <div className="rounded-xl border border-[#16233C] bg-[#0A1120] p-3.5">
                  <h3 className="text-[13px] font-bold text-white mb-2">📏 Rules — yehi exact thresholds lage (WMO/IMD small-craft)</h3>
                  <ul className="space-y-1 text-[11px] text-[#9FB0D1]">
                    <li><span className="text-red-300 font-bold">DANGER</span> wave ≥ 4.0 m (ab ya next 48 h mein kabhi bhi)</li>
                    <li><span className="text-red-300 font-bold">DANGER</span> gust ≥ 34 kn (WMO gale threshold)</li>
                    <li><span className="text-amber-300 font-bold">CAUTION</span> wave ≥ 2.5 m (48 h window included)</li>
                    <li><span className="text-amber-300 font-bold">CAUTION</span> wind ≥ 20 kn within 48 h (Beaufort 5)</li>
                    <li><span className="text-sky-300 font-bold">NOTE</span> current &gt; 3 kn → strong-current note (state nahi badalta)</li>
                    <li className="text-[#4D5D80]">Fold = WORST point decides · average kabhi nahi · land_unverified ≠ safe</li>
                  </ul>
                </div>
                <div className="rounded-xl border border-[#16233C] bg-[#0A1120] p-3.5">
                  <h3 className="text-[13px] font-bold text-white mb-2">🧪 Method + sources (sab auditable)</h3>
                  <div className="text-[11px] text-[#9FB0D1] leading-relaxed">{ra.method}</div>
                  <div className="mt-2 text-[10.5px] text-[#4D5D80]">
                    land: {ra.land_reason ?? "—"} · fetched at {(ra.fetched_at ?? "").replace("T", " ").slice(0, 19)}Z
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(ra.sources_used ?? []).map((s) => (
                      <span key={s} className="rounded px-1.5 py-0.5 text-[9.5px] font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
                        ✔ {s}
                      </span>
                    ))}
                    {(ra.sources_failed ?? []).map((s) => (
                      <span key={s} className="rounded px-1.5 py-0.5 text-[9.5px] font-bold bg-red-500/10 text-red-300 border border-red-500/30">
                        ✗ {s} (failed — chhupaya nahi)
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
