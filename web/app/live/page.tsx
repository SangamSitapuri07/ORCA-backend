"use client";

/* B19+B20 — ORCA Live Beacon "Samudri Rakshak Net" (web lab).
 * MRCC-style dispatch + watch/listen mode + ORCA Radio + rescue nav.
 *   LISTEN  → bina beacon ke bhi SOS sune (position ~11km ROUND, privacy)
 *   MAYDAY  → 1-tap SOS; backend khud nearest boats trace karta hai
 *   RELAY   → unke ping mein hi RESCUE REQUEST → FULL-SCREEN alert
 *   ACK     → ✅ MADAD KARUNGA → dono taraf live doori/ETA + RADIO
 *   NAV     → rescuer apna route-check/route-advisory analyze kar sakta
 *   ESCALATE→ 60s no-accept → radius 10→25→50 NM
 * Is page pe koi fake/demo boat invent nahi hota — sab backend se. */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  CaseMsg,
  LiveBoat,
  LiveNearbyResponse,
  LiveStats,
  MySosStatus,
  RescueRequestPayload,
  RouteAdvisory,
  fetchRouteAdvisory,
  fmtLat,
  fmtLon,
  liveBoat,
  liveNearby,
  livePing,
  liveRescueAnswer,
  liveRescueComplete,
  liveRescueMsg,
  liveSos,
  liveSosClear,
  liveStart,
  liveStats,
  liveStop,
} from "@/lib/orca-client";

type Phase = "idle" | "active";

const SESS_KEY = "orca.live.session";
const PUB_KEY = "orca.live.pubid";
const LABEL_KEY = "orca.live.label";
const WATCH_ID_KEY = "orca.live.watchid";
/* B22: har release ka visible tag — ab ek nazar mein pakdo ki page pe
 * NAYA code serve ho raha hai ya kisi ZOMBIE dev server ka purana.
 * (User ka demo isi confusion se toota tha — port 3000 pe stale UI.) */
const WEB_BUILD = "B22";

/* B22: watch id PER-WINDOW (sessionStorage) — pehle localStorage tha jo
 * saare windows SHARE karte hain. Same-browser demo mein Window A aur B
 * ka watch id SAME ho jaata tha → B ke listen-pings A ke beacon ko
 * overwrite karte the aur dispatch khud-victim ko request kabhi nahi
 * bhejta — "notification + navigation nahi aa raha" ka ASLI root cause. */
function getWatchId(): string {
  let s = sessionStorage.getItem(WATCH_ID_KEY) ?? "";
  if (!s) {
    s = (crypto.randomUUID?.() ?? `w${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`).replace(/-/g, "").slice(0, 24);
    sessionStorage.setItem(WATCH_ID_KEY, s);
  }
  return s;
}

const C = {
  bg: "bg-[#0A0E1A]",
  card: "bg-[#121A2E] border border-[#1E2A44]",
  faint: "text-[#4D5D80]",
  body: "text-[#9FB0D1]",
  input:
    "w-full bg-[#0A0E1A] border border-[#1E2A44] rounded-lg px-3 py-2 text-sm text-white placeholder:text-[#34446A] focus:outline-none focus:border-cyan-500/60",
};

const PRESETS = [
  "🌊 leher zyada hai",
  "🔋 battery 20% bachi",
  "⛽ fuel kam hai",
  "🧊 paani ghus raha hai",
  "📍 position same hai",
  "👥 4 log hain boat pe",
  "🩹 chot lagi hai",
  "👍 theek hoon abhi",
];

function fmtAge(sec: number): string {
  if (sec < 60) return `${Math.max(0, Math.round(sec))}s pehle`;
  if (sec < 3600) return `${Math.round(sec / 60)} min pehle`;
  return `${(sec / 3600).toFixed(1)} h pehle`;
}

function compass(deg: number): string {
  const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return dirs[Math.round(((deg % 360) + 360) % 360 / 45) % 8];
}

function Trend({ prev, cur }: { prev: number | undefined; cur: number }) {
  if (prev === undefined) return null;
  if (cur < prev - 0.02) return <span className="text-emerald-400 font-bold" title="qareeb aa raha">↓</span>;
  if (cur > prev + 0.02) return <span className="text-amber-400 font-bold" title="door ja raha">↑</span>;
  return <span className="text-[#4D5D80]">→</span>;
}

/* ── ORCA Radio — case comms (victim ↔ accepted rescuer). Feed ping
 *    ke andar hi aata hai; koi extra polling nahi. ── */
function CaseComms({ messages, onSend, busy, accent }: {
  messages: CaseMsg[];
  onSend: (text: string, preset: boolean) => void;
  busy: boolean;
  accent: "red" | "emerald";
}) {
  const [txt, setTxt] = useState("");
  const ring = accent === "red" ? "border-red-500/40" : "border-emerald-500/40";
  const mine = accent === "red" ? "bg-red-500/20 text-red-100" : "bg-emerald-500/20 text-emerald-100";
  return (
    <div className={`mt-3 rounded-xl border ${ring} bg-black/30 p-3`}>
      <div className={`text-[10px] font-bold tracking-wider ${C.faint} mb-2`}>📻 ORCA RADIO — live channel (victim ↔ rescuer)</div>
      <div className="space-y-1.5 max-h-40 overflow-y-auto mb-2">
        {messages.length === 0 && <div className={`text-[11px] ${C.faint}`}>Abhi koi message nahi — presets se shuru karo, ek tap mein jaata hai.</div>}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.mine ? "justify-end" : "justify-start"}`}>
            <span className={`text-[12px] rounded-lg px-2.5 py-1.5 max-w-[85%] ${m.mine ? mine : "bg-[#1E2A44]/60 text-white"}`}>
              {m.preset ? "⚡ " : ""}{m.text}
              <span className={`block text-[9px] opacity-60`}>{m.mine ? "tum" : m.from} · {fmtAge(m.age_sec)}</span>
            </span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1 mb-2">
        {PRESETS.map((p) => (
          <button key={p} disabled={busy} onClick={() => onSend(p, true)}
            className="text-[10px] bg-[#0A0E1A] hover:bg-[#0E1526] border border-[#1E2A44] rounded-lg px-2 py-1 text-[#9FB0D1]">
            {p}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input value={txt} onChange={(e) => setTxt(e.target.value)} maxLength={140}
          onKeyDown={(e) => { if (e.key === "Enter" && txt.trim()) { onSend(txt.trim(), false); setTxt(""); } }}
          placeholder="message likho (140c)…"
          className="flex-1 bg-[#0A0E1A] border border-[#1E2A44] rounded-lg px-2.5 py-1.5 text-xs text-white placeholder:text-[#34446A] focus:outline-none" />
        <button disabled={busy || !txt.trim()} onClick={() => { onSend(txt.trim(), false); setTxt(""); }}
          className="text-xs bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/50 rounded-lg px-3 py-1.5 text-cyan-100 disabled:opacity-40">
          bhejo
        </button>
      </div>
    </div>
  );
}

/* ── SVG rescue radar ── */
function Radar({ boats, radiusNm, selfSos }: {
  boats: LiveBoat[];
  radiusNm: number;
  selfSos: boolean;
}) {
  const size = 300;
  const cx = size / 2;
  const maxR = size / 2 - 16;
  const px = maxR / radiusNm;
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[330px] mx-auto select-none" role="img" aria-label="rescue radar">
      <circle cx={cx} cy={cx} r={maxR + 8} fill="#0A1020" stroke="#1E2A44" />
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <circle key={f} cx={cx} cy={cx} r={maxR * f} fill="none" stroke="#16233C" strokeDasharray={f === 1 ? "" : "3 4"} />
      ))}
      <line x1={cx} y1={10} x2={cx} y2={size - 10} stroke="#16233C" />
      <line x1={10} y1={cx} x2={size - 10} y2={cx} stroke="#16233C" />
      <text x={cx + 4} y={24} fill="#4D5D80" fontSize={10}>N</text>
      <text x={cx + maxR - 10} y={cx - 4} fill="#4D5D80" fontSize={9}>{radiusNm} NM</text>
      <text x={cx + maxR / 2 - 8} y={cx - 4} fill="#33436B" fontSize={9}>{Math.round(radiusNm / 2)} NM</text>
      <circle cx={cx} cy={cx} r={7} fill={selfSos ? "#EF4444" : "#22D3EE"} opacity={0.25} />
      <circle cx={cx} cy={cx} r={4} fill={selfSos ? "#EF4444" : "#22D3EE"} />
      {boats.map((b) => {
        const d = Math.min(b.distance_nm ?? radiusNm, radiusNm);
        const brg = (((b.bearing_deg ?? 0) % 360) + 360) % 360;
        const rad = (brg * Math.PI) / 180;
        const x = cx + d * px * Math.sin(rad);
        const y = cx - d * px * Math.cos(rad);
        return (
          <g key={b.pub_id}>
            {b.sos && (
              <circle cx={x} cy={y} r={6} fill="none" stroke="#EF4444" strokeWidth={1.6}>
                <animate attributeName="r" from="6" to="16" dur="1.4s" repeatCount="indefinite" />
                <animate attributeName="opacity" from="0.9" to="0" dur="1.4s" repeatCount="indefinite" />
              </circle>
            )}
            {b.on_rescue && !b.sos && <circle cx={x} cy={y} r={8} fill="none" stroke="#2DD4BF" strokeWidth={1.4} strokeDasharray="3 2" />}
            <circle cx={x} cy={y} r={b.sos ? 5.5 : 4} fill={b.sos ? "#EF4444" : b.on_rescue ? "#2DD4BF" : "#64748B"} stroke={b.sos ? "#FCA5A5" : "#94A3B8"} strokeWidth={0.8} />
            <text x={x + 8} y={y + 3} fill={b.sos ? "#FCA5A5" : b.on_rescue ? "#5EEAD4" : "#64748B"} fontSize={9} fontFamily="monospace">
              {b.label ?? b.pub_id}{typeof b.distance_nm === "number" ? ` · ${b.distance_nm}NM` : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function LiveBeaconPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [session, setSession] = useState("");
  const [pubId, setPubId] = useState("");
  const [label, setLabel] = useState("");
  const [latTxt, setLatTxt] = useState("13.08");
  const [lonTxt, setLonTxt] = useState("80.29");
  const [intervalSec, setIntervalSec] = useState(5);
  const [pings, setPings] = useState(0);
  const [lastPingAt, setLastPingAt] = useState<number | null>(null);
  const [sos, setSos] = useState(false);
  const [sosNote, setSosNote] = useState("");
  const [sosConfirmUntil, setSosConfirmUntil] = useState(0);
  const [stopConfirmUntil, setStopConfirmUntil] = useState(0);
  const [mySos, setMySos] = useState<MySosStatus | null>(null);
  const [resolvedMsg, setResolvedMsg] = useState<string | null>(null);
  const [rescueReq, setRescueReq] = useState<RescueRequestPayload | null>(null);
  const [rescueEndedMsg, setRescueEndedMsg] = useState<string | null>(null);
  const [nearbyRes, setNearbyRes] = useState<LiveNearbyResponse | null>(null);
  const [netStats, setNetStats] = useState<LiveStats | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [accTrends, setAccTrends] = useState<Record<string, number>>({});
  const [trackId, setTrackId] = useState<string | null>(null);
  const [trackBoat, setTrackBoat] = useState<LiveBoat | null>(null);
  const [trackErr, setTrackErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  // B20: watch mode
  const [watchOn, setWatchOn] = useState(true);
  const [watchPings, setWatchPings] = useState(0);
  // B20: rescue route analysis
  const [navBusy, setNavBusy] = useState(false);
  const [navRes, setNavRes] = useState<RouteAdvisory | null>(null);
  const [navErr, setNavErr] = useState<string | null>(null);

  const coordsRef = useRef<{ lat: number; lon: number }>({ lat: 13.08, lon: 80.29 });
  const sessionRef = useRef("");
  sessionRef.current = session;
  const sosRef = useRef(false);
  sosRef.current = sos;
  const prevAccRef = useRef<Record<string, number>>({});
  const prevRescDistRef = useRef<number | null>(null);
  const resolvedShownRef = useRef<string | null>(null);
  const labelRef = useRef("");
  labelRef.current = label;
  const rescueWasAcceptedRef = useRef(false);
  const sirenRef = useRef<{ stop: () => void } | null>(null);

  const myCoords = useCallback((): { lat: number; lon: number } | null => {
    const lat = parseFloat(latTxt);
    const lon = parseFloat(lonTxt);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
    coordsRef.current = { lat, lon };
    return { lat, lon };
  }, [latTxt, lonTxt]);

  /* B21 FIX: type kiye coords turant pings mein laagu ho — pehle sirf
   * start/SOS/analyze pe sync hota tha (coords change → position nahi
   * badalti thi ping mein — demo-wire-up bug jo user ne pakda) */
  useEffect(() => { myCoords(); }, [myCoords]);

  /* ── siren (fullscreen alert) — WebAudio, koi file nahi ──
   * B22 FIX: Chrome ka autoplay rule — bina user-gesture ke AudioContext
   * SUSPENDED rehta hai (sound bilkul nahi bajti — "notification nahi
   * aaya" ka ek hissa). Pehle click/type pe context bana ke RESUME kar
   * lete hain; siren usi UNLOCKED context pe bajegi. */
  const audioCtxRef = useRef<AudioContext | null>(null);
  useEffect(() => {
    const unlock = () => {
      try {
        const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AC) return;
        audioCtxRef.current = audioCtxRef.current ?? new AC();
        void audioCtxRef.current.resume();
      } catch { /* noop */ }
    };
    window.addEventListener("pointerdown", unlock, { once: true });
    window.addEventListener("keydown", unlock, { once: true });
    return () => {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    };
  }, []);

  const startSiren = useCallback(() => {
    try {
      navigator.vibrate?.([400, 150, 400, 150, 400, 300, 600]);
      const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AC) return;
      const ctx = audioCtxRef.current ?? new AC();  // unlocked ctx reuse (nahi to suspended)
      audioCtxRef.current = ctx;
      void ctx.resume();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      gain.gain.value = 0.06;
      osc.connect(gain).connect(ctx.destination);
      osc.start();
      let hi = true;
      const t = setInterval(() => { osc.frequency.value = hi ? 880 : 620; hi = !hi; }, 550);
      sirenRef.current = {
        stop: () => {
          clearInterval(t);
          try { osc.stop(); } catch { /* noop */ }  // ctx reuse hoga — close MAT karo
        },
      };
    } catch { /* autoplay blocked — visual alert to chalega hi */ }
  }, []);
  const stopSiren = useCallback(() => {
    sirenRef.current?.stop();
    sirenRef.current = null;
    try { navigator.vibrate?.(0); } catch { /* noop */ }
  }, []);

  /* ── mount: rescue mode? session? watch id? stats? ── */
  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search);
      const t = q.get("track");
      if (t) setTrackId(t);
      let s = sessionStorage.getItem(SESS_KEY);
      const p = sessionStorage.getItem(PUB_KEY);
      const l = sessionStorage.getItem(LABEL_KEY);
      if (s && p) {
        setLabel(l ?? "");
        setPubId(p);
        setPhase("active");
      } else {
        s = getWatchId();  // B22: per-window (shared localStorage se windows collide karte the)
      }
      if (s) setSession(s);
    } catch { /* SSR safety */ }
    liveStats().then(setNetStats).catch(() => setNetStats(null));
  }, []);

  /* ── ping loop (beacon ON) — ping hi alert channel hai ── */
  useEffect(() => {
    if (phase !== "active" || !session) return;
    let cancelled = false;
    const beat = async () => {
      const c = coordsRef.current;
      try {
        const r = await livePing(sessionRef.current, c.lat, c.lon, { label: labelRef.current || undefined });
        if (cancelled) return;
        setPings((n) => n + 1);
        setLastPingAt(Date.now());
        setErr(null);
        setMySos(r.my_sos);
        const hadAccepted = rescueWasAcceptedRef.current;
        rescueWasAcceptedRef.current = r.rescue_request?.my_state === "accepted";
        setRescueReq(r.rescue_request);
        if (hadAccepted && !r.rescue_request && !cancelled) {
          setRescueEndedMsg("Rescue case band ho gaya — victim theek ho gaya ya rescue complete ho gaya. 🙏");
        }
        if (!r.rescue_request) prevRescDistRef.current = null;
        if (r.sos_resolved && resolvedShownRef.current !== r.sos_resolved.case_id) {
          resolvedShownRef.current = r.sos_resolved.case_id;
          setSos(false); setMySos(null);
          setResolvedMsg(r.sos_resolved.by === "rescuer"
            ? "✅ RESCUE HO GAYA — rescuer ne 'pahunch gaya / sab safe' mark kiya. Tumhara SOS auto-clear ho gaya."
            : "SOS case close ho gaya.");
        }
      } catch (e) {
        if (!cancelled) setErr(`Ping fail — network/backend? (${e instanceof Error ? e.message : String(e)}) — ORCA retry karta rahega.`);
      }
    };
    beat();
    const t = setInterval(beat, Math.max(3, intervalSec) * 1000);
    return () => { cancelled = true; clearInterval(t); };
  }, [phase, session, intervalSec]);

  /* ── WATCH loop (beacon OFF) — bina beacon ke bhi SOS sune ── */
  useEffect(() => {
    if (phase !== "idle" || !watchOn || trackId || !session) return;
    let cancelled = false;
    const beat = async () => {
      const c = coordsRef.current;
      try {
        const r = await livePing(sessionRef.current, c.lat, c.lon, { watch: true });
        if (cancelled) return;
        setWatchPings((n) => n + 1);
        // request aayi toh fullscreen alert state mein aa jaayenge
        setRescueReq((prev) => {
          const next = r.rescue_request;
          if (prev?.my_state === "accepted" && !next) {
            setRescueEndedMsg("Rescue case band ho gaya. 🙏");
          }
          return prev?.my_state === "accepted" && !next ? null : (next ?? prev);
        });
      } catch { /* watch silent-fail: listener mode kabhi err page nahi dikhata */ }
    };
    beat();
    const t = setInterval(beat, 12_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [phase, watchOn, trackId, session]);

  /* ── siren control: fullscreen alert ke saath ── */
  const showFullAlert = rescueReq !== null && rescueReq.my_state !== "accepted";
  useEffect(() => {
    if (showFullAlert) startSiren();
    else stopSiren();
    return () => stopSiren();
  }, [showFullAlert, startSiren, stopSiren]);

  /* victim: accepted rescuers ke distance trends */
  useEffect(() => {
    if (!mySos) { prevAccRef.current = {}; setAccTrends({}); return; }
    const trends: Record<string, number> = {};
    for (const a of mySos.accepted) trends[a.pub_id] = prevAccRef.current[a.pub_id] ?? a.distance_nm;
    prevAccRef.current = Object.fromEntries(mySos.accepted.map((a) => [a.pub_id, a.distance_nm]));
    setAccTrends(trends);
  }, [mySos]);

  /* ── radar refresh ── */
  useEffect(() => {
    if (phase !== "active" && !trackId) return;
    let cancelled = false;
    const pull = async () => {
      const c = coordsRef.current;
      try {
        const r = await liveNearby(c.lat, c.lon, 20);
        if (!cancelled) setNearbyRes(r);
      } catch { if (!cancelled) setNearbyRes(null); }
    };
    pull();
    const t = setInterval(pull, 10_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [phase, trackId]);

  /* ── rescue view poll (family / share link) ── */
  useEffect(() => {
    if (!trackId) return;
    let cancelled = false;
    const pull = async () => {
      try {
        const r = await liveBoat(trackId);
        if (!cancelled) { setTrackBoat(r.boat); setTrackErr(null); }
      } catch (e) {
        if (!cancelled) { setTrackBoat(null); setTrackErr(e instanceof Error ? e.message : String(e)); }
      }
    };
    pull();
    const t = setInterval(pull, 5_000);
    return () => { cancelled = true; clearInterval(t); };
  }, [trackId]);

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  void tick;

  const useMyGps = () => {
    if (!navigator.geolocation) { setErr("Is browser mein geolocation nahi — coords type kar do."); return; }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => { setLatTxt(pos.coords.latitude.toFixed(5)); setLonTxt(pos.coords.longitude.toFixed(5)); setBusy(false); },
      () => { setErr("GPS permission mila nahi — coords manually type kar do (demo ke liye best)."); setBusy(false); },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const startBeacon = async () => {
    const c = myCoords();
    if (!c) { setErr("Sahi lat/lon daalo pehle (±90 / ±180 ke andar)."); return; }
    setBusy(true);
    try {
      const r = await liveStart(c.lat, c.lon, label.trim() || undefined, session || undefined);
      setSession(r.session); setPubId(r.pub_id); setPhase("active"); setErr(null);
      try {
        sessionStorage.setItem(SESS_KEY, r.session);
        sessionStorage.setItem(PUB_KEY, r.pub_id);
        sessionStorage.setItem(LABEL_KEY, label.trim());
      } catch { /* private mode */ }
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  };

  const fireSos = async () => {
    const nowT = Date.now();
    if (sosConfirmUntil < nowT) { setSosConfirmUntil(nowT + 4000); return; }
    setSosConfirmUntil(0);
    const c = myCoords();
    setBusy(true);
    try {
      const r = await liveSos(session, sosNote.trim() || undefined, c?.lat, c?.lon);
      setSos(true);
      setMySos(r.case);
      setResolvedMsg(null);
      setErr(null);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  };

  const clearSos = async () => {
    setBusy(true);
    try {
      await liveSosClear(session);
      setSos(false); setMySos(null); setErr(null);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  };

  const answerRescue = async (accept: boolean) => {
    if (!rescueReq) return;
    setBusy(true);
    try {
      if (accept && phase !== "active") {
        // watch listener → beacon upgrade (consent: khud MADAD dabaya)
        const c = myCoords();
        if (c) {
          const r = await liveStart(c.lat, c.lon, label.trim() || "ORCA rescuer", session || undefined);
          setSession(r.session); setPubId(r.pub_id); setPhase("active");
          try {
            sessionStorage.setItem(SESS_KEY, r.session);
            sessionStorage.setItem(PUB_KEY, r.pub_id);
          } catch { /* noop */ }
        }
      }
      const r = await liveRescueAnswer(sessionRef.current, rescueReq.case_id, accept);
      if (accept && r.rescue) { setRescueReq(r.rescue); rescueWasAcceptedRef.current = true; }
      if (!accept) setRescueReq(null);
      setErr(null);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  };

  const completeRescue = async () => {
    if (!rescueReq) return;
    setBusy(true);
    try {
      await liveRescueComplete(sessionRef.current, rescueReq.case_id);
      setRescueReq(null);
      setNavRes(null);
      setRescueEndedMsg("✅ TUMNE RESCUE COMPLETE MARK KIYA — ek zindagi bachayi. Victim ka SOS auto-clear ho gaya. 🙏");
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  };

  const sendMsg = async (caseId: string, text: string, preset: boolean) => {
    try { await liveRescueMsg(sessionRef.current, caseId, text, preset); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  };

  /* 🧭 B20: rescuer apna rescue route intelligently analyze kare —
   * same battle-tested route-check/advisory engine (GLOBE land mask
   * + 48h wave/wind/gust per point) jo voyage flow chalata hai. */
  const analyzeRescueRoute = async () => {
    if (!rescueReq) return;
    setNavBusy(true); setNavErr(null); setNavRes(null);
    // B21: 0.5 NM se kam — zero-length route ko API pe mat bhejo
    if (rescueReq.distance_nm < 0.5) {
      setNavBusy(false);
      setNavErr(`Victim bahut paas hai (${rescueReq.distance_nm} NM) — route analysis ki zaroorat nahi; seedha ${rescueReq.bearing_deg}° ${compass(rescueReq.bearing_deg)} pe jao.`);
      return;
    }
    try {
      const c = coordsRef.current;
      const r = await fetchRouteAdvisory(c.lat, c.lon, rescueReq.victim.lat, rescueReq.victim.lon);
      setNavRes(r);
    } catch (e) {
      setNavErr(e instanceof Error ? e.message : String(e));
    }
    setNavBusy(false);
  };

  const stopBeacon = async () => {
    const nowT = Date.now();
    if (stopConfirmUntil < nowT) { setStopConfirmUntil(nowT + 4000); return; }
    setStopConfirmUntil(0);
    setBusy(true);
    try { await liveStop(session); } catch { /* best-effort */ }
    try { sessionStorage.removeItem(SESS_KEY); sessionStorage.removeItem(PUB_KEY); sessionStorage.removeItem(LABEL_KEY); } catch { /* noop */ }
    let wid = session; try { wid = getWatchId(); } catch { /* noop */ }
    setSession(wid);  // B22: wapas is window ke apne watch id pe
    setPubId(""); setPhase("idle"); setSos(false); setMySos(null);
    setRescueReq(null); setResolvedMsg(null); setRescueEndedMsg(null); setNavRes(null);
    setPings(0); setLastPingAt(null); setNearbyRes(null);
    liveStats().then(setNetStats).catch(() => setNetStats(null));
    setBusy(false);
  };

  const shareUrl = typeof window !== "undefined" && pubId
    ? `${window.location.origin}/live?track=${pubId}` : `/live?track=${pubId}`;

  const copyShare = async () => {
    try { await navigator.clipboard.writeText(shareUrl); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { setErr("Clipboard block hai — link manually copy kar lo."); }
  };

  const otherBoats = (nearbyRes?.boats ?? []).filter((b) => b.pub_id !== pubId);
  const rescTrendPrev = rescueReq ? (prevRescDistRef.current ?? undefined) : undefined;
  if (rescueReq) prevRescDistRef.current = rescueReq.distance_nm;

  /* ══ RESCUE VIEW (share link — family) ══ */
  if (trackId) {
    return (
      <div className={`min-h-screen ${C.bg} text-white flex flex-col items-center px-4 py-6`}>
        <div className="w-full max-w-lg">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-lg font-bold tracking-tight">🆘 RESCUE VIEW <span className={C.faint + " text-xs font-normal"}>Samudri Rakshak Net</span> <span className="ml-1 rounded-md border border-[#1E2A44] px-1.5 py-0.5 text-[9px] font-mono text-cyan-300/80 align-middle">{WEB_BUILD}</span></h1>
            <button onClick={() => { setTrackId(null); history.replaceState(null, "", "/live"); }}
              className="text-xs text-cyan-300 hover:text-cyan-200 border border-[#1E2A44] rounded-lg px-3 py-1.5">← beacon apna</button>
          </div>
          {/* B21: is page ka role CLEAR karo — ye buttons wala rescuer
              console NAHI hai (user ne yahin notifications dhoondhe) */}
          <div className="mb-4 rounded-xl border border-cyan-400/40 bg-cyan-400/5 px-4 py-3 text-xs text-cyan-100/90 leading-relaxed">
            👪 <b>Ye READ-ONLY family tracking page hai</b> — link jo family/team ko bheji jaati hai, sirf DEKHNE ke liye.
            <b> Madad karne wale rescuer ke liye</b> main page kholo (<span className="font-mono">/live</span>) — wahan Watch mode apne aap ON hai aur SOS ka <b>full-screen alert + accept button</b> aata hai.
          </div>
          {trackErr && (
            <div className={`${C.card} rounded-xl p-4 text-sm text-amber-300/90 leading-relaxed`}>
              ⚠️ {trackErr}
              <div className={`mt-2 text-xs ${C.faint}`}>ORCA kabhi purani/fake position nahi dikhata.</div>
            </div>
          )}
          {trackBoat && (
            <div className={`rounded-xl p-4 border ${trackBoat.sos ? "border-red-500/60 bg-red-950/30" : C.card}`}>
              {trackBoat.sos && (
                <div className="flex items-center gap-2 mb-3">
                  <span className="relative flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
                  </span>
                  <span className="text-red-300 font-bold text-sm tracking-wide">SOS ACTIVE — madad chahiye</span>
                </div>
              )}
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <div className={C.faint}>Boat</div>
                <div className="font-mono text-white">{trackBoat.label ?? trackBoat.pub_id}</div>
                <div className={C.faint}>Position</div>
                <div className="font-mono text-cyan-300">{fmtLat(trackBoat.lat)}, {fmtLon(trackBoat.lon)}</div>
                <div className={C.faint}>Last ping</div>
                <div className={trackBoat.age_sec > 120 ? "text-amber-300" : "text-emerald-300"}>{fmtAge(trackBoat.age_sec)}{trackBoat.age_sec > 120 ? " — purana" : " — LIVE"}</div>
                {trackBoat.sos_note && (<><div className={C.faint}>Message</div><div className="text-amber-200">{trackBoat.sos_note}</div></>)}
              </div>
              <div className={`mt-3 pt-3 border-t border-[#1E2A44] text-xs ${C.faint} leading-relaxed`}>
                📡 Har 5 sec auto-refresh · VHF Ch 16 · Indian Coast Guard <span className="text-white font-semibold">1554</span>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  /* ══ MAIN ══ */
  return (
    <div className={`min-h-screen ${C.bg} text-white flex flex-col items-center px-4 py-6`}>

      {/* ═══ FULL-SCREEN RESCUE ALERT (warning-notification style) ═══ */}
      {showFullAlert && rescueReq && (
        <div className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center p-4">
          <div className="absolute inset-2 sm:inset-4 rounded-3xl border-4 border-red-500 animate-pulse pointer-events-none" />
          <div className="w-full max-w-md text-center relative">
            <div className="text-6xl mb-2 animate-bounce">🆘</div>
            <div className="text-2xl sm:text-3xl font-black text-red-400 tracking-tight leading-tight">
              PAAS MEIN HELP<br />MAANGI GAYI HAI!
            </div>
            <div className="mt-1 text-sm text-red-200/80">ek ORCA boat mushkil mein hai — tum sabse kareeb ho</div>

            <div className="mt-5 bg-red-950/40 border border-red-500/50 rounded-2xl p-4 text-left">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-lg font-bold text-white">{rescueReq.victim.label ?? "ORCA boat"}</span>
                <span className="text-[10px] font-mono text-red-300/70">SOS {rescueReq.victim.sos_age_sec !== undefined ? fmtAge(rescueReq.victim.sos_age_sec) : ""}</span>
              </div>
              {rescueReq.victim.sos_note && <div className="text-amber-200 text-sm mt-1">&ldquo;{rescueReq.victim.sos_note}&rdquo;</div>}
              <div className="mt-3 flex items-center justify-center gap-3">
                <div className="text-center">
                  <div className="text-4xl font-black text-white">{rescueReq.distance_nm}<span className="text-lg text-red-300"> NM</span></div>
                  <div className="text-[10px] text-red-300/70 tracking-wider">DOORI TUMSE</div>
                </div>
                <div className="text-5xl text-red-400" style={{ transform: `rotate(${rescueReq.bearing_deg}deg)` }}>➤</div>
                <div className="text-center">
                  <div className="text-4xl font-black text-white">{rescueReq.bearing_deg}°</div>
                  <div className="text-[10px] text-red-300/70 tracking-wider">{compass(rescueReq.bearing_deg)} DISHA</div>
                </div>
              </div>
              <div className={`mt-2 text-center text-[11px] ${rescueReq.expires_in_sec < 120 ? "text-red-400" : "text-red-200/60"}`}>
                ⏳ request {Math.floor(rescueReq.expires_in_sec / 60)}:{String(rescueReq.expires_in_sec % 60).padStart(2, "0")} min mein expire
              </div>
            </div>

            <button onClick={() => answerRescue(true)} disabled={busy}
              className="mt-5 w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-[#032117] font-black rounded-2xl px-6 py-5 text-xl shadow-[0_0_40px_rgba(16,185,129,0.35)]">
              ✅ HAAN — MAIN AA RAHA HOON
            </button>
            <button onClick={() => answerRescue(false)} disabled={busy}
              className="mt-2 w-full bg-transparent border border-[#1E2A44] hover:border-red-500/40 text-[#9FB0D1] rounded-2xl px-6 py-3 text-sm">
              ❌ nahi paaunga (request doosri boats pe jaayegi)
            </button>
            <div className="mt-3 text-[10px] text-[#4D5D80]">Accept karne par tumhari EXACT live position victim ke saath share hogi (consent = tumhara tap). Mana karo toh kuch share nahi hota.</div>
          </div>
        </div>
      )}

      <div className="w-full max-w-5xl">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div>
            <h1 className="text-lg font-bold tracking-tight">📡 Live Beacon <span className="text-cyan-300/90">· Samudri Rakshak Net</span> <span className="ml-1 rounded-md border border-[#1E2A44] px-1.5 py-0.5 text-[9px] font-mono text-cyan-300/80 align-middle">{WEB_BUILD}</span></h1>
            <p className={`text-xs ${C.faint} mt-0.5`}>1-tap SOS → system KHUD paas ke boats trace karke request bhejta hai — bina beacon ke bhi SUN sakte ho (watch mode)</p>
          </div>
          <Link href="/" className="text-xs text-cyan-300 hover:text-cyan-200 border border-[#1E2A44] rounded-lg px-3 py-1.5">← ORCA home</Link>
        </div>

        {err && <div className="mb-4 rounded-xl border border-red-500/50 bg-red-950/30 px-4 py-3 text-sm text-red-200">{err}</div>}

        {/* ═══ RESCUER GUIDANCE (accepted — in-page) ═══ */}
        {rescueReq && rescueReq.my_state === "accepted" && (
          <div className="mb-4 rounded-xl border-2 border-emerald-500 bg-emerald-950/30 px-4 py-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="relative flex h-3.5 w-3.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-500" />
              </span>
              <span className="font-bold text-emerald-200">🚤 TUM MADAD PE JA RAHE HO — live guidance</span>
            </div>
            <div className="grid sm:grid-cols-3 gap-2 text-sm mb-1">
              <div className="bg-black/30 border border-[#1E2A44] rounded-lg px-3 py-2">
                <div className={`text-[10px] ${C.faint}`}>Victim</div>
                <div className="font-semibold text-white">{rescueReq.victim.label ?? rescueReq.victim.pub_id}</div>
                {rescueReq.victim.sos_note && <div className="text-[11px] text-amber-200 mt-0.5">&ldquo;{rescueReq.victim.sos_note}&rdquo;</div>}
                <div className="mt-1 font-mono text-[11px] text-cyan-300">{fmtLat(rescueReq.victim.lat)}, {fmtLon(rescueReq.victim.lon)}</div>
              </div>
              <div className="bg-black/30 border border-[#1E2A44] rounded-lg px-3 py-2">
                <div className={`text-[10px] ${C.faint}`}>Doori · disha (har ping taaza)</div>
                <div className="font-bold text-lg text-white">
                  {rescueReq.distance_nm} NM <Trend prev={rescTrendPrev} cur={rescueReq.distance_nm} />
                  <span className={`text-sm ${C.body}`}> · {rescueReq.bearing_deg}° {compass(rescueReq.bearing_deg)}</span>
                  <span className="inline-block text-emerald-300" style={{ transform: `rotate(${rescueReq.bearing_deg}deg)` }}> ➤</span>
                </div>
              </div>
              <div className="bg-black/30 border border-[#1E2A44] rounded-lg px-3 py-2">
                <div className={`text-[10px] ${C.faint}`}>SOS kitna purana</div>
                <div className="text-white">{rescueReq.victim.sos_age_sec !== undefined ? fmtAge(rescueReq.victim.sos_age_sec) : "—"}</div>
              </div>
            </div>

            {/* 🧭 rescue route intelligence */}
            <div className="mt-2">
              <button onClick={analyzeRescueRoute} disabled={navBusy}
                className="w-full bg-sky-500/15 hover:bg-sky-500/25 border border-sky-400/50 rounded-xl px-4 py-3 text-sm font-bold text-sky-200 disabled:opacity-50">
                {navBusy ? "⏳ route analyze ho raha (weather + land mask)…" : "🧭 RESCUE ROUTE ANALYZE KARO — kya main safe pahunch paunga?"}
              </button>
              {navErr && <div className="mt-2 text-[11px] text-amber-300/90">⚠️ {navErr} — ORCA guess nahi karega; compass bearing upar se lo.</div>}
              {navRes && (
                <div className="mt-2 rounded-xl border border-sky-400/40 bg-black/30 p-3 text-[12px]">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`font-black px-2 py-0.5 rounded ${navRes.verdict.level === "go" ? "bg-emerald-500/20 text-emerald-300" : navRes.verdict.level === "caution" ? "bg-amber-500/20 text-amber-300" : navRes.verdict.level === "nogo" ? "bg-red-500/20 text-red-300" : "bg-slate-500/20 text-slate-300"}`}>
                      {navRes.verdict.level === "go" ? "✅ JA SAKTE HO" : navRes.verdict.level === "caution" ? "⚠️ SAVDHANI SE" : navRes.verdict.level === "nogo" ? "⛔ KHATARNAAK — mat jao" : "❓ VERIFY NAHI"}
                    </span>
                    <span className="text-white font-semibold">{navRes.distance_nm.toFixed(1)} NM</span>
                    {navRes.rerouted && <span className="text-sky-300">↩️ land se ghuma ke {navRes.waypoints?.length ?? 0} waypoints</span>}
                    <span className={C.faint}>{navRes.verdict.points_known}/{navRes.verdict.points_total} points forecast mille</span>
                  </div>
                  <div className={`mt-1.5 ${C.faint} leading-relaxed`}>
                    {(() => {
                      const worst = navRes.points.find((p) => p.state === "danger") ?? navRes.points.find((p) => p.state === "caution");
                      return worst
                        ? `Sabse kharab point ${worst.sail_km.toFixed(0)} km pe: ${worst.why ?? "forecast dekho"}`
                        : navRes.land_ok === false
                          ? `⚠️ seedhi line LAND se guzarti hai — reroute follow karo`
                          : `Poora rasta analyze — 48h forecast mein koi danger point nahi mila.`;
                    })()}
                    {navRes.land_ok === null && " · ⚠️ land-mask verify nahi hua — coast ke paas dhyan se"}
                  </div>
                </div>
              )}
            </div>

            <CaseComms messages={rescueReq.messages} busy={busy} accent="emerald"
              onSend={(t, p) => sendMsg(rescueReq.case_id, t, p)} />

            <button onClick={completeRescue} disabled={busy}
              className="mt-3 w-full bg-emerald-600 hover:bg-emerald-500 font-bold rounded-xl px-4 py-3.5 text-white">
              ✅ PAHUNCH GAYA / SAB SAFE — rescue complete
            </button>
          </div>
        )}

        {rescueEndedMsg && !rescueReq && (
          <div className="mb-4 rounded-xl border border-emerald-500/50 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-200 flex items-start justify-between gap-3">
            <span>{rescueEndedMsg}</span>
            <button onClick={() => setRescueEndedMsg(null)} className="text-emerald-300/70 hover:text-emerald-200 text-xs shrink-0">✕</button>
          </div>
        )}

        {/* ═══ MERA SOS + DISPATCH STATUS + RADIO ═══ */}
        {sos && (
          <div className="mb-4 rounded-xl border-2 border-red-500 bg-red-950/50 px-4 py-4">
            <div className="flex items-center gap-2">
              <span className="relative flex h-3.5 w-3.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-red-500" />
              </span>
              <span className="text-red-200 font-bold">SOS BROADCAST HO RAHA HAI 🔴</span>
            </div>

            {mySos && (
              <>
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="text-xs bg-black/40 border border-red-500/40 rounded-lg px-2.5 py-1.5 text-red-100">🛰️ <b>{mySos.dispatched}</b> ko request gayi ({mySos.tier_nm} NM)</span>
                  <span className="text-xs bg-black/40 border border-[#1E2A44] rounded-lg px-2.5 py-1.5 text-[#9FB0D1]">👀 <b>{mySos.seen}</b> ne dekha</span>
                  {mySos.declined > 0 && <span className="text-xs bg-black/40 border border-[#1E2A44] rounded-lg px-2.5 py-1.5 text-[#9FB0D1]">❌ <b>{mySos.declined}</b> ne mana</span>}
                  <span className={`text-xs rounded-lg px-2.5 py-1.5 border ${mySos.accepted.length ? "border-emerald-400/60 bg-emerald-400/10 text-emerald-200" : "border-[#1E2A44] bg-black/40 text-[#4D5D80]"}`}>
                    ✅ <b>{mySos.accepted.length}</b> AA {mySos.accepted.length === 1 ? "RAHA HAI" : "RAHE HAIN"}
                  </span>
                </div>

                {mySos.status === "open" && mySos.accepted.length === 0 && (
                  <div className="mt-2 text-xs text-amber-300/90 bg-amber-400/10 border border-amber-400/30 rounded-lg px-3 py-2">
                    ⏳ {mySos.escalate_in_sec !== null
                      ? `Koi accept nahi? System KHUD radius badha dega — abhi ${mySos.tier_nm} NM, ${mySos.escalate_in_sec}s mein ${mySos.tiers_nm[Math.min(mySos.tiers_nm.indexOf(mySos.tier_nm) + 1, mySos.tiers_nm.length - 1)]} NM tak aur boats ko request.`
                      : `Maximum radius (${mySos.tier_nm} NM) tak request jaa chuki — Coast Guard 1554 / VHF Ch 16 bhi try karo.`}
                  </div>
                )}

                {mySos.accepted.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {mySos.accepted.map((a) => (
                      <div key={a.pub_id} className="rounded-xl border border-emerald-400/50 bg-emerald-950/30 px-4 py-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-emerald-300 font-bold">🚤 {a.label ?? "ORCA boat"} MADAD PE AA RAHA HAI</span>
                          {typeof a.eta_min === "number"
                            ? <span className="text-xs bg-emerald-400/20 border border-emerald-400/40 rounded-lg px-2 py-1 text-emerald-100">ETA ~{a.eta_min} min</span>
                            : <span className={`text-xs ${C.faint}`}>(doori live dekho — ETA invent nahi karenge)</span>}
                        </div>
                        <div className="mt-1 text-sm text-emerald-100">
                          <b className="text-lg">{a.distance_nm} NM</b> <Trend prev={accTrends[a.pub_id]} cur={a.distance_nm} /> · {a.bearing_deg}° {compass(a.bearing_deg)}
                          <span className="inline-block text-emerald-300" style={{ transform: `rotate(${a.bearing_deg}deg)` }}> ➤</span>
                          <span className={`text-xs ml-2 ${a.age_sec > 60 ? "text-amber-300" : C.faint}`}>· ping {fmtAge(a.age_sec)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {mySos.accepted.length > 0 && (
                  <CaseComms messages={mySos.messages} busy={busy} accent="red"
                    onSend={(t, p) => sendMsg(mySos.case_id, t, p)} />
                )}
              </>
            )}

            <div className="mt-3 text-xs text-red-300/80">Himmat rakho. Coast Guard <span className="font-bold text-white">1554</span> · VHF Ch 16 (SOLAS Reg 33: paas ki ships legally aane ko bound hain).</div>
            <div className={`mt-2 pt-2 border-t border-red-500/20 flex items-center gap-2 flex-wrap`}>
              <span className={`text-[10px] ${C.faint}`}>family backup link:</span>
              <code className="text-[10px] bg-black/40 border border-red-500/30 rounded-lg px-2 py-1 text-red-100/80 break-all">{shareUrl}</code>
              <button onClick={copyShare} className="text-[10px] bg-red-500/10 hover:bg-red-500/20 border border-red-400/40 rounded-lg px-2 py-1 text-red-100/80">
                {copied ? "✅ copied" : "copy"}
              </button>
            </div>
          </div>
        )}

        {resolvedMsg && !sos && (
          <div className="mb-4 rounded-xl border border-emerald-500/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-200 flex items-start justify-between gap-3">
            <span>{resolvedMsg}</span>
            <button onClick={() => setResolvedMsg(null)} className="text-emerald-300/70 hover:text-emerald-200 text-xs shrink-0">✕</button>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
          {/* ── LEFT: beacon control ── */}
          <div className={`${C.card} rounded-xl p-4`}>
            {phase === "idle" ? (
              <>
                <h2 className="text-sm font-bold text-white mb-1">▶️ Beacon shuru karo</h2>
                <p className={`text-xs ${C.body} mb-3 leading-relaxed`}>
                  Voyage ke waqt tumhara phone ek AIS-transponder ban jaata hai — anonymous, tumhare control mein.
                </p>

                {/* WATCH MODE strip */}
                <div className={`mb-3 rounded-xl border px-3 py-2.5 flex items-center gap-2 ${watchOn ? "border-cyan-400/40 bg-cyan-400/5" : "border-[#1E2A44]"}`}>
                  <span className="text-base">👂</span>
                  <div className="flex-1 min-w-0">
                    <div className={`text-xs font-semibold ${watchOn ? "text-cyan-300" : C.body}`}>
                      Watch mode {watchOn ? "ON" : "OFF"} {watchOn && <span className={C.faint}>· {watchPings} listen-pings</span>}
                    </div>
                    <div className={`text-[10px] ${C.faint} leading-snug`}>
                      Bina beacon ke bhi paas ke SOS ka <b>full-screen alert</b> aa jaayega. Privacy: position ~11 km tak <b>round</b> ho ke jaati hai — exact trail kabhi nahi.
                      {watchOn && <span className="block mt-0.5 text-amber-300/80">🔊 Siren ke liye page pe <b>ek tap</b> kar dena (Chrome ka sound-unlock rule) — alert khud aayega.</span>}
                    </div>
                  </div>
                  <button onClick={() => setWatchOn((v) => !v)}
                    className={`text-[10px] rounded-lg px-2 py-1.5 border shrink-0 ${watchOn ? "border-cyan-400/60 text-cyan-300" : "border-[#1E2A44] text-[#4D5D80]"}`}>
                    {watchOn ? "band" : "chalu"}
                  </button>
                </div>

                <label className={`block text-xs ${C.faint} mb-1`}>Boat ka naam <span className="text-[#34446A]">(optional)</span></label>
                <input className={`${C.input} mb-3`} value={label} onChange={(e) => setLabel(e.target.value)} maxLength={40} placeholder="e.g. SeaStar · Chennai" />
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div>
                    <label className={`block text-xs ${C.faint} mb-1`}>Latitude</label>
                    <input className={C.input} value={latTxt} onChange={(e) => setLatTxt(e.target.value)} inputMode="decimal" />
                  </div>
                  <div>
                    <label className={`block text-xs ${C.faint} mb-1`}>Longitude</label>
                    <input className={C.input} value={lonTxt} onChange={(e) => setLonTxt(e.target.value)} inputMode="decimal" />
                  </div>
                </div>
                <div className="flex gap-2 mb-3">
                  <button onClick={useMyGps} disabled={busy} className="flex-1 text-xs bg-[#0A0E1A] hover:bg-[#0E1526] border border-[#1E2A44] rounded-lg px-3 py-2 text-[#9FB0D1]">📍 Meri GPS location</button>
                  <button onClick={() => { setLatTxt("13.08000"); setLonTxt("80.29000"); }} className="text-xs bg-[#0A0E1A] hover:bg-[#0E1526] border border-[#1E2A44] rounded-lg px-3 py-2 text-[#4D5D80]" title="Pehli boat (victim) demo coords">boat-1 demo</button>
                  <button onClick={() => { setLatTxt("13.10000"); setLonTxt("80.31000"); }} className="text-xs bg-[#0A0E1A] hover:bg-[#0E1526] border border-[#1E2A44] rounded-lg px-3 py-2 text-cyan-300/90" title="Doosri boat (rescuer) — 1.7 NM door">boat-2 demo</button>
                </div>
                <div className={`text-[10px] ${C.faint} mb-3 -mt-1`}>demo mein 2 windows ke coords <b>ALAG</b> rakho (boat-1 vs boat-2) — warna sab 0 NM dikhega.</div>
                <button onClick={startBeacon} disabled={busy} className="w-full bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-[#06202A] font-bold rounded-xl px-4 py-3 text-sm transition-colors">
                  {busy ? "⏳ shuru ho raha…" : "🟢 VOYAGE BEACON SHURU KARO"}
                </button>
                {netStats && (
                  <div className={`mt-3 text-[11px] ${C.faint} text-center`}>
                    abhi <span className="text-cyan-300 font-semibold">{netStats.active_boats}</span> beacons + <span className="text-cyan-300/80">{netStats.watchers}</span> listeners · <span className={netStats.sos_active > 0 ? "text-red-400 font-semibold" : ""}>{netStats.sos_active}</span> SOS
                  </div>
                )}
                <div className={`mt-4 pt-3 border-t border-[#1E2A44] text-[11px] ${C.faint} leading-relaxed`}>
                  <span className="text-[#9FB0D1] font-semibold">SOS ke baad (sab automatic):</span><br />
                  1️⃣ backend paas ke beacons + listeners trace karta hai<br />
                  2️⃣ unhe <b>full-screen alert</b> aata hai — ✅ madad / ❌ mana<br />
                  3️⃣ jo accept kare: live doori+ETA + 📻 ORCA Radio channel<br />
                  4️⃣ 60s mein koi accept nahi → 10→25→50 NM escalate<br />
                  5️⃣ rescuer apna <b>rescue route (weather+land)</b> bhi analyze kar sakta hai
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className={`relative flex h-3 w-3`}>
                      <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${sos ? "bg-red-400" : "bg-emerald-400"} opacity-75`} />
                      <span className={`relative inline-flex rounded-full h-3 w-3 ${sos ? "bg-red-500" : "bg-emerald-400"}`} />
                    </span>
                    <span className={`text-sm font-bold ${sos ? "text-red-300" : "text-emerald-300"}`}>{sos ? "SOS broadcasting" : "Beacon LIVE"}</span>
                  </div>
                  <span className={`text-[10px] font-mono ${C.faint}`}>id {pubId}</span>
                </div>

                <div className="grid grid-cols-3 gap-2 mb-3 text-center">
                  <div className="bg-[#0A0E1A] border border-[#1E2A44] rounded-lg py-2">
                    <div className="text-lg font-bold text-white">{pings}</div>
                    <div className={`text-[9px] ${C.faint}`}>pings bheje</div>
                  </div>
                  <div className="bg-[#0A0E1A] border border-[#1E2A44] rounded-lg py-2">
                    <div className="text-lg font-bold text-white">{lastPingAt ? `${Math.round((Date.now() - lastPingAt) / 1000)}s` : "—"}</div>
                    <div className={`text-[9px] ${C.faint}`}>last ping age</div>
                  </div>
                  <div className="bg-[#0A0E1A] border border-[#1E2A44] rounded-lg py-2">
                    <div className="text-lg font-bold text-white">{nearbyRes?.count ?? 0}</div>
                    <div className={`text-[9px] ${C.faint}`}>boats 20 NM</div>
                  </div>
                </div>

                <div className="flex items-center gap-2 mb-3">
                  <label className={`text-xs ${C.faint}`}>Ping gap:</label>
                  {[5, 30].map((s) => (
                    <button key={s} onClick={() => setIntervalSec(s)}
                      className={`text-xs rounded-lg px-3 py-1.5 border ${intervalSec === s ? "border-cyan-400/60 text-cyan-300 bg-cyan-400/10" : "border-[#1E2A44] text-[#4D5D80]"}`}>
                      {s}s {s === 5 ? "(demo)" : "(asli voyage)"}
                    </button>
                  ))}
                </div>

                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div>
                    <label className={`block text-xs ${C.faint} mb-1`}>Latitude</label>
                    <input className={C.input} value={latTxt} onChange={(e) => setLatTxt(e.target.value)} inputMode="decimal" />
                  </div>
                  <div>
                    <label className={`block text-xs ${C.faint} mb-1`}>Longitude</label>
                    <input className={C.input} value={lonTxt} onChange={(e) => setLonTxt(e.target.value)} inputMode="decimal" />
                  </div>
                </div>

                <input className={`${C.input} mb-3`} value={sosNote} onChange={(e) => setSosNote(e.target.value)} maxLength={140}
                  placeholder="SOS message (optional): 'engine fail, paani aa raha hai'" />

                {!sos ? (
                  <button onClick={fireSos} disabled={busy}
                    className={`w-full font-bold rounded-xl px-4 py-4 text-base transition-all ${sosConfirmUntil > Date.now()
                      ? "bg-red-500 text-white animate-pulse"
                      : "bg-red-950/60 hover:bg-red-900/60 text-red-300 border-2 border-red-500/70"}`}>
                    {sosConfirmUntil > Date.now() ? "⚠️ PAKKA? Dubara dabao — SOS chala jaayega" : "🚨 SOS — MUSHKIL MEIN HOON"}
                  </button>
                ) : (
                  <button onClick={clearSos} disabled={busy}
                    className="w-full bg-emerald-600 hover:bg-emerald-500 font-bold rounded-xl px-4 py-4 text-base text-white">
                    ✅ MAIN THEEK HOON — SOS band karo
                  </button>
                )}

                <button onClick={stopBeacon} disabled={busy}
                  className={`mt-2 w-full text-xs rounded-xl px-4 py-2.5 border transition-colors ${stopConfirmUntil > Date.now()
                    ? "border-amber-400/70 text-amber-300 bg-amber-400/10"
                    : "border-[#1E2A44] text-[#4D5D80] hover:text-[#9FB0D1]"}`}>
                  {stopConfirmUntil > Date.now() ? "⚠️ pakka? beacon band = position turant DELETE" : "⏹️ Voyage khatam — beacon band karo (poora delete)"}
                </button>

                <div className={`mt-3 text-[10px] ${C.faint} leading-relaxed`}>
                  Privacy promise: raw session id sirf tumhare paas — public mein sirf {pubId} dikhta hai. Beacon band ya 2 ghante silence → position ka koi record nahi bachta.
                </div>
              </>
            )}
          </div>

          {/* ── RIGHT: radar + boats ── */}
          <div className={`${C.card} rounded-xl p-4`}>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-bold text-white">🛰️ Paas ke ORCA boats <span className={`font-normal ${C.faint}`}>(20 NM · 10s refresh)</span></h2>
              <span className={`text-[10px] font-mono ${C.faint}`}>{phase === "active" ? "LIVE" : watchOn ? "👂 watching" : "radar beacon ON pe jagega"}</span>
            </div>

            {phase === "active" ? (
              <>
                <Radar boats={otherBoats} radiusNm={20} selfSos={sos} />
                <div className="mt-3 space-y-2">
                  {otherBoats.length === 0 && (
                    <div className={`text-xs ${C.faint} text-center py-4 border border-dashed border-[#1E2A44] rounded-xl`}>
                      Abhi 20 NM mein koi doosri beacon-boat nahi{nearbyRes?.watchers ? ` (${nearbyRes.watchers} listeners sun rahe hain — invisible hain)` : ""}.
                    </div>
                  )}
                  {otherBoats.map((b) => (
                    <div key={b.pub_id}
                      className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 ${b.sos ? "border-red-500/60 bg-red-950/30" : "border-[#1E2A44] bg-[#0A0E1A]"}`}>
                      <span className={`inline-block h-2.5 w-2.5 rounded-full ${b.sos ? "bg-red-500 animate-pulse" : b.on_rescue ? "bg-teal-400" : "bg-slate-500"}`} />
                      <div className="min-w-0 flex-1">
                        <div className={`text-sm truncate ${b.sos ? "text-red-200 font-semibold" : "text-white"}`}>
                          {b.label ?? "ORCA boat"} <span className={`font-mono text-[10px] ${C.faint}`}>{b.pub_id}</span>
                          {b.on_rescue && !b.sos && <span className="ml-1.5 text-[10px] bg-teal-400/15 border border-teal-400/40 rounded px-1.5 py-0.5 text-teal-300">🚤 madad mein</span>}
                        </div>
                        <div className={`text-[11px] ${C.faint}`}>
                          {typeof b.distance_nm === "number" ? `${b.distance_nm} NM` : "? NM"}
                          {typeof b.bearing_deg === "number" ? ` · ${b.bearing_deg}° ${compass(b.bearing_deg)}` : ""} · ping {fmtAge(b.age_sec)}
                          {b.sos && b.sos_note ? ` · "${b.sos_note}"` : ""}
                        </div>
                      </div>
                      {typeof b.bearing_deg === "number" && (
                        <span className={`text-base ${b.sos ? "text-red-300" : "text-slate-400"}`} style={{ transform: `rotate(${b.bearing_deg}deg)`, display: "inline-block" }}>➤</span>
                      )}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className={`text-xs ${C.faint} text-center py-10 border border-dashed border-[#1E2A44] rounded-xl leading-relaxed px-6`}>
                {watchOn
                  ? <>👂 <b className="text-cyan-300">WATCH MODE LIVE</b> — beacon ke bina bhi paas ka SOS seedha <b>full-screen alert</b> ban ke aayega.<br />
                    <span className="text-[#34446A]">Demo: Window A beacon @ 13.08,80.29 → SOS · Window B sirf yeh page khuli (watch ON) → B pe siren + fullscreen popup sirf ~12 sec mein!</span></>
                  : <>Watch mode OFF hai — SOS alerts nahi aayenge. Upar se chalu karo ya beacon shuru karo.</>}
              </div>
            )}

            <div className={`mt-4 pt-3 border-t border-[#1E2A44] text-[10px] ${C.faint} leading-relaxed`}>
              <span className="text-[#9FB0D1] font-semibold">Honesty:</span> sab kuch backend ke REAL pings se — koi fake/demo boat nahi. Watch mode ~11 km rounded privacy ke saath. Request marzi se accept hoti hai. ETA sirf real speed pe. 12 h purana SOS auto-delete. ORCA Radio case ke saath wipe hoti hai.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
