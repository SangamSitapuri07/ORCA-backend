"use client";

/**
 * 🆘 SOS / zero-internet emergency panel.
 *
 * Honest physics, told plainly:
 *  - GPS needs NO internet (satellites) — your position keeps working.
 *  - Satellite/API data needs internet — when it's gone we say so and
 *    show only what's REAL and LOCAL: your position, last-known data
 *    timestamps, and this panel's built-in helpers.
 *  - CONTACT: a phone's GSM voice/SMS signal works in far weaker
 *    coverage than data; the real offshore channel is VHF Channel 16.
 *    This panel makes all three one tap away — no invented "satellite
 *    messenger" that a smartphone can't actually be.
 *
 * Everything here is bundled/client-side (harbour list is compiled into
 * the JS) — it opens and computes with ZERO network.
 */
import { useEffect, useMemo, useState } from "react";
import { Lang } from "@/lib/i18n";
import { HARBOURS } from "@/lib/harbours";
import { haversineKm, bearingDeg, compass } from "@/lib/marine-math";
import { fmtLat, fmtLon } from "@/lib/orca-client";

export type SosFix = {
  lat: number; lon: number; acc: number;
  speed: number | null; heading: number | null; ts: number;
};

const CONTACT_KEY = "orca_sos_contact";

export default function SosPanel({
  lat, lon, gps, gpsOn, online, lang, onClose, onStartGps,
}: {
  lat: number; lon: number;
  gps: SosFix | null;
  gpsOn: boolean;
  online: boolean;
  lang: Lang;
  onClose: () => void;
  onStartGps: () => void;
}) {
  const [contact, setContact] = useState("");
  const [saved, setSaved] = useState(false);
  const [nowTick, setNowTick] = useState(0);

  useEffect(() => {
    try { setContact(localStorage.getItem(CONTACT_KEY) ?? ""); } catch { /* private mode */ }
    const t = setInterval(() => setNowTick((n) => n + 1), 15000);
    return () => clearInterval(t);
  }, []);

  const saveContact = (v: string) => {
    setContact(v);
    setSaved(true);
    try { localStorage.setItem(CONTACT_KEY, v.trim()); } catch { /* ok */ }
  };

  // position: live GPS when present, else the map anchor — always labelled
  const posLive = !!gps;
  const pLat = gps?.lat ?? lat;
  const pLon = gps?.lon ?? lon;
  const pAcc = gps?.acc ?? null;
  const spKn = gps?.speed != null && gps.speed >= 0 ? gps.speed * 1.943844 : null;
  const tsUtc = new Date(gps?.ts ?? Date.now()).toISOString().replace("T", " ").slice(0, 19) + " UTC";
  void nowTick;

  const nearest = useMemo(() => {
    return HARBOURS.map((h) => {
      const km = haversineKm(pLat, pLon, h.lat, h.lon);
      return {
        h,
        nm: km / 1.852,
        brg: bearingDeg(pLat, pLon, h.lat, h.lon),
        etaMin: spKn && spKn > 0.5 ? (km / 1.852 / spKn) * 60 : null,
      };
    }).sort((a, b) => a.nm - b.nm).slice(0, 3);
  }, [pLat, pLon, spKn]);

  const smsBody = encodeURIComponent(
    `ORCA SOS: position ${pLat.toFixed(5)},${pLon.toFixed(5)}`
    + (pAcc != null ? ` (accuracy ±${Math.round(pAcc)}m)` : " (manual anchor — GPS off)")
    + ` at ${tsUtc}`
    + (spKn != null ? `, speed ${spKn.toFixed(1)} kn` : "")
    + ". Need assistance. (sent via ORCA offline SOS)"
  );
  const contactNum = contact.trim().replace(/[^\d+]/g, "");
  const isTouch = typeof navigator !== "undefined" && /Android|iPhone|iPad/i.test(navigator.userAgent);

  return (
    <div className="absolute inset-0 z-[3000] bg-[#070D1A]/97 overflow-y-auto p-4 fade-up">
      <div className="max-w-[520px] mx-auto space-y-3 pb-8">
        <div className="flex items-center justify-between">
          <div className="font-bold text-red-300 text-base">🆘 {lang === "hi" ? "आपात स्थिति (SOS)" : "Emergency (SOS)"}</div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-xl px-2" aria-label="close">✕</button>
        </div>

        {/* network truth */}
        <div className={`rounded-lg border px-3 py-2 text-[11px] ${online
          ? "border-emerald-500/40 bg-emerald-950/50 text-emerald-200"
          : "border-red-500/40 bg-red-950/60 text-red-200"}`}>
          {online
            ? (lang === "hi" ? "📡 इंटरनेट चालू है" : "📡 internet ON")
            : (lang === "hi"
              ? "📡 इंटरनेट नहीं — पर GPS चल रहा है (सैटेलाइट सीधा phone से बात करता है, इंटरनेट से नहीं)"
              : "📡 no internet — GPS still works (satellites talk to the phone directly)")}
        </div>

        {/* position — big and readable */}
        <div className="rounded-xl border border-[#24405f] bg-[#0A1120] p-3.5 space-y-1">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            {lang === "hi" ? "आपकी position" : "your position"}
            {posLive
              ? ` · LIVE GPS${pAcc != null ? ` (±${Math.round(pAcc)}m)` : ""}`
              : (lang === "hi" ? " · मैप बिंदु (GPS बंद)" : " · map point (GPS off)")}
          </div>
          <div className="font-mono text-2xl text-cyan-200 font-bold">
            {fmtLat(pLat)} {fmtLon(pLon)}
          </div>
          <div className="text-[11px] text-slate-400">{tsUtc}</div>
          {!gpsOn && (
            <button onClick={onStartGps}
              className="mt-1 text-[11px] rounded-md border border-sky-400/50 text-sky-300 px-2.5 py-1.5 hover:bg-sky-500/10">
              📍 {lang === "hi" ? "LIVE GPS चालू करो" : "enable LIVE GPS"}
            </button>
          )}
        </div>

        {/* contact actions — the REAL channels that need no data */}
        <div className="rounded-xl border border-[#24405f] bg-[#0A1120] p-3.5 space-y-2.5">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            {lang === "hi" ? "संपर्क — बिना इंटरनेट काम करने वाले channels" : "contact — channels that work without internet"}
          </div>
          <a href="tel:1554"
            className="flex items-center justify-between rounded-lg bg-red-500/15 border border-red-500/40 px-3 py-2.5 text-red-200 font-bold hover:bg-red-500/25">
            <span>📞 {lang === "hi" ? "भारतीय Coast Guard" : "Indian Coast Guard"}</span>
            <span className="font-mono text-xl">1554</span>
          </a>
          <div className="space-y-1.5">
            <label className="text-[10px] text-slate-500">
              {lang === "hi" ? "आपका emergency contact (एक बार डालो — phone में सेव रहेगा)" : "your emergency contact (saved on device)"}
            </label>
            <input
              value={contact}
              onChange={(e) => saveContact(e.target.value)}
              placeholder={lang === "hi" ? "जैसे +91 98xxxxxx45" : "e.g. +91 98xxxxxx45"}
              inputMode="tel"
              className="w-full rounded-md bg-[#0E1B30] border border-[#24405f] px-3 py-2 text-sm text-white placeholder:text-slate-600"
            />
            {saved && contactNum && <div className="text-[10px] text-emerald-400">✓ {lang === "hi" ? "सेव हो गया" : "saved"}</div>}
          </div>
          {contactNum && (
            <div className="grid grid-cols-2 gap-2">
              <a href={`tel:${contactNum}`}
                className="text-center rounded-lg bg-[#0E1B30] border border-[#24405f] px-3 py-2.5 text-slate-200 font-semibold hover:bg-[#132540]">
                📞 {lang === "hi" ? "Call" : "Call"}
              </a>
              <a href={`sms:${contactNum}?&body=${smsBody}`}
                className="text-center rounded-lg bg-emerald-500/15 border border-emerald-500/40 px-3 py-2.5 text-emerald-200 font-semibold hover:bg-emerald-500/25">
                ✉️ SMS position
              </a>
            </div>
          )}
          <div className="text-[10.5px] text-slate-500 leading-snug">
            {isTouch
              ? (lang === "hi"
                ? "SMS सिर्फ 1-bar GSM signal में भी चला जाता है — internet की ज़रूरत नहीं। खुले आसमान रखो, थोड़ा wait करो।"
                : "SMS rides bare GSM signalling — works with far weaker signal than data.")
              : (lang === "hi"
                ? "SMS भेजना phone पर खोलो (laptop में SMS app नहीं होता — यह सीमा browser की है, app की नहीं)।"
                : "SMS sending needs a phone (desktops have no SMS app — browser limit, honestly shown).")}
          </div>
          <div className="rounded-lg bg-[#0E1B30] border border-[#24405f] px-3 py-2 text-[11px] text-slate-300">
            📻 <b>VHF Channel 16</b> — {lang === "hi"
              ? "समुद्र में असली distress channel (हर बड़ी boat/Coast Guard सुनती है)। Boat में VHF set हो तो यही पहला रास्ता है।"
              : "the real distress channel at sea — every ship & the Coast Guard monitors it."}
          </div>
        </div>

        {/* nearest harbours — fully offline (bundled real list) */}
        <div className="rounded-xl border border-[#24405f] bg-[#0A1120] p-3.5 space-y-2">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            {lang === "hi" ? "सबसे नज़दीकी बंदरगाह (offline list — 71 असली)" : "nearest harbours (offline list — 71 real)"}
          </div>
          {nearest.map(({ h, nm, brg, etaMin }, i) => (
            <div key={h.name} className="flex items-center justify-between rounded-lg bg-[#0E1B30] px-3 py-2 text-[12px]">
              <span className="text-slate-200 font-medium">#{i + 1} ⚓ {h.name}</span>
              <span className="text-slate-400 text-right">
                <b className="text-cyan-200">{nm.toFixed(1)} NM</b> {Math.round(brg)}° {compass(brg)}
                {etaMin != null && (
                  <div className="text-[10px] text-emerald-300">
                    ETA {etaMin >= 60 ? `${Math.floor(etaMin / 60)}h ${Math.round(etaMin % 60)}m` : `${Math.round(etaMin)} min`}
                  </div>
                )}
              </span>
            </div>
          ))}
          <div className="text-[10px] text-slate-600">
            {lang === "hi"
              ? "Positions public charts से (~0.5 NM) — GLOBE mask से verify; ETA आपकी current GPS speed का है।"
              : "Positions from public charts (~0.5 NM), land-mask verified; ETA uses your current GPS speed."}
          </div>
        </div>
      </div>
    </div>
  );
}
