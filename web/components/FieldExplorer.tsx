"use client";

/**
 * Visual Explorer — full-screen REAL map (OpenStreetMap tiles, same as
 * the main map) where every dot is a REAL sampled measurement around
 * the clicked point. Six switchable layers, one per data family:
 *   🛰️ Chlorophyll (NOAA VIIRS sampled pixels; no catch/PFZ inference)
 *   🌊 Waves       (height, m — Open-Meteo marine model)
 *   〰️ Swell        (long-period swell, m)
 *   💨 Wind gusts  (kn — the number that capsizes small boats)
 *   🌀 Current     (surface current, kn)
 *   🌡️ SST         (sea-surface temperature, °C)
 * Plus the 48 h evidence charts (same arrays as the verdict) and the
 * ranked high-chlorophyll list. Values come from API responses; decorative
 * rendering is not an observed fish/catch layer, and failures show their error.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { MapContainer, TileLayer, Circle, CircleMarker, Tooltip, Polyline } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import LineChart from "@/components/LineChart";
import { Lang } from "@/lib/i18n";
import {
  fetchField, fetchRouteCheck, FieldPoint, FieldResponse, RouteCheckResponse, fmtLat, fmtLon,
} from "@/lib/orca-client";
import { chlColor, waveColor, windColor, currentColor, sstColor } from "@/components/fieldColors";

const Ocean3D = dynamic(() => import("@/components/Ocean3D"), { ssr: false });

/* navigation math lives in lib/marine-math.ts (shared with the SOS
 * panel): haversine distance, bearing, cross-track — pure client-side,
 * offline-capable; there is no road graph at sea, guidance IS a course
 * line like every real chartplotter. */
import { bearingDeg, compass, crossTrackKm, haversineKm } from "@/lib/marine-math";
import { useOnline } from "@/lib/useOnline";
import SosPanel, { SosFix } from "@/components/SosPanel";

type Trend = {
  labels: string[];
  wave_m: (number | null)[];
  swell_m?: (number | null)[];
  wind_kn: (number | null)[];
  gust_kn: (number | null)[];
  current_kn?: (number | null)[];
  sst_c?: (number | null)[];
};

type LayerId = "chl" | "wave" | "swell" | "wind" | "current" | "sst";

const LAYERS: {
  id: LayerId; label: string; labelHi: string; unit: string;
  color: (v: number) => string;
  radius: (v: number) => number;
  legend: string; legendHi: string;
  fromChl?: boolean;
}[] = [
  {
    id: "chl", label: "Chlorophyll", labelHi: "क्लोरोफिल", unit: "mg/m³",
    color: chlColor, fromChl: true,
    radius: (v) => Math.min(13, 4 + Math.sqrt(v) * 3),
    legend: "display bands: <0.5 · 0.5-2 · 2-5 · >5 mg/m³ (not a HAB/PFZ test)",
    legendHi: "दिखाने की श्रेणी: <0.5 · 0.5-2 · 2-5 · >5 mg/m³ (HAB/PFZ जाँच नहीं)",
  },
  {
    id: "wave", label: "Waves", labelHi: "लहरें", unit: "m",
    color: waveColor,
    radius: (v) => Math.min(12, 3.5 + v * 2.2),
    legend: "waves: <1.2 calm · 1.2-2.5 workable · 2.5-4 caution · >4 unsafe",
    legendHi: "लहरें: <1.2 शांत · 1.2-2.5 चलने लायक · 2.5-4 सावधानी · >4 खतरनाक",
  },
  {
    id: "swell", label: "Swell", labelHi: "उमड़ी (swell)", unit: "m",
    color: waveColor,
    radius: (v) => Math.min(12, 3.5 + v * 2.2),
    legend: "swell: long rollers — ≥2.5 m makes landing/beaching risky",
    legendHi: "swell: लंबी उमड़ती लहरें — 2.5 m+ पर किनारे उतरना जोखिम",
  },
  {
    id: "wind", label: "Wind gusts", labelHi: "हवा (gusts)", unit: "kn",
    color: windColor,
    radius: (v) => Math.min(12, 3 + v * 0.28),
    legend: "gusts: <15 fine · 15-28 watchful · 28-34 caution · >34 gale",
    legendHi: "झोंके: <15 ठीक · 15-28 नज़र रखें · 28-34 सावधानी · >34 तूफ़ान",
  },
  {
    id: "current", label: "Current", labelHi: "धारा", unit: "kn",
    color: currentColor,
    radius: (v) => Math.min(12, 3.5 + v * 2),
    legend: "current: <0.6 weak · 0.6-1.5 normal · 1.5-3 strong · >3 very strong",
    legendHi: "धारा: <0.6 कमज़ोर · 0.6-1.5 सामान्य · 1.5-3 तेज़ · >3 बहुत तेज़",
  },
  {
    id: "sst", label: "SST", labelHi: "समुद्र तापमान", unit: "°C",
    color: sstColor,
    radius: () => 8,  // SST varies by fractions of a degree — colour honestly, no fake sizing
    legend: "SST display bands: <26 · 26-28.5 · 28.5-30 · >30°C (no species inference)",
    legendHi: "SST दिखाने की श्रेणी: <26 · 26-28.5 · 28.5-30 · >30°C (मछली अनुमान नहीं)",
  },
];

export default function FieldExplorer({
  lat, lon, lang, trend, onClose,
}: {
  lat: number; lon: number;
  lang: Lang;
  trend?: Trend | null;          // advisory hourly_chart when available
  onClose: () => void;
}) {
  const [data, setData] = useState<FieldResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [layer, setLayer] = useState<LayerId>("chl");
  const [view, setView] = useState<"map" | "3d">("map");

  // ── marine navigation state (all REAL: phone GPS + haversine + the
  //    backend's GLOBE-mask route verification; nothing simulated) ──
  type GpsFix = SosFix;
  type Hotspot = FieldResponse["hotspots"][number];
  const [gpsOn, setGpsOn] = useState(false);
  const [gps, setGps] = useState<GpsFix | null>(null);
  const [gpsErr, setGpsErr] = useState<string | null>(null);
  const [navTarget, setNavTarget] = useState<Hotspot | null>(null);
  const [route, setRoute] = useState<RouteCheckResponse | null>(null);
  const [routeBusy, setRouteBusy] = useState(false);
  const [seaMarks, setSeaMarks] = useState(false);
  const watchRef = useRef<number | null>(null);
  const online = useOnline();
  const [sos, setSos] = useState(false);

  // ── trip TRACE: breadcrumb track of where the boat actually went.
  //    Points are the device's own GPS fixes (20 m jitter filter), kept
  //    in localStorage so a browser refresh never loses the day. ──
  type TrackPt = [number, number, number]; // lat, lon, epoch-ms
  const [tripOn, setTripOn] = useState(false);
  const [track, setTrack] = useState<TrackPt[]>([]);
  const [tripStart, setTripStart] = useState<number | null>(null);

  useEffect(() => {   // restore a saved trip after refresh (local data only)
    try {
      const raw = localStorage.getItem("orca_trip_track");
      if (raw) {
        const j = JSON.parse(raw);
        if (Array.isArray(j.points) && j.points.length > 1) {
          setTrack(j.points);
          setTripStart(j.started ?? null);
        }
      }
    } catch { /* storage blocked — trace just won't persist */ }
  }, []);

  const clearTrip = () => {
    setTrack([]); setTripStart(null);
    try { localStorage.removeItem("orca_trip_track"); } catch { /* ok */ }
  };

  const stopGps = () => {
    if (watchRef.current != null) { navigator.geolocation.clearWatch(watchRef.current); watchRef.current = null; }
    setGpsOn(false);
    setTripOn(false);
  };
  const startGps = () => {
    setGpsErr(null);
    if (typeof window === "undefined" || !("geolocation" in navigator)) {
      setGpsErr(lang === "hi" ? "इस browser में GPS नहीं है" : "no geolocation in this browser");
      return;
    }
    if (!window.isSecureContext) {
      // Browser geolocation requires a secure context. Do not imply that a
      // fisher's phone can use the development machine's loopback address.
      setGpsErr(lang === "hi"
        ? "GPS के लिए यह पेज सुरक्षित HTTPS से खोलें।"
        : "Open this page through secure HTTPS to use GPS.");
      return;
    }
    setGpsOn(true);
    watchRef.current = navigator.geolocation.watchPosition(
      (fix) => setGps({
        lat: fix.coords.latitude, lon: fix.coords.longitude,
        acc: fix.coords.accuracy, speed: fix.coords.speed,
        heading: fix.coords.heading, ts: fix.timestamp,
      }),
      (e) => {
        setGpsErr(lang === "hi"
          ? `GPS error: ${e.message} (permission di? location on hai?)`
          : `GPS error: ${e.message}`);
        stopGps();
      },
      { enableHighAccuracy: true, maximumAge: 3000, timeout: 20000 },
    );
  };
  useEffect(() => () => {           // unmount cleanup
    if (watchRef.current != null) navigator.geolocation.clearWatch(watchRef.current);
  }, []);

  // breadcrumb recorder: appends each REAL fix while trip is on
  useEffect(() => {
    if (!gps || !tripOn) return;
    setTrack((prev) => {
      const last = prev[prev.length - 1];
      if (last && haversineKm(last[0], last[1], gps.lat, gps.lon) < 0.02) return prev; // <20 m = GPS jitter
      const next = [...prev, [gps.lat, gps.lon, gps.ts] as TrackPt].slice(-3000);
      try {
        localStorage.setItem("orca_trip_track",
          JSON.stringify({ points: next, started: tripStart ?? gps.ts }));
      } catch { /* storage full/blocked — trace still lives in memory */ }
      return next;
    });
    setTripStart((s) => s ?? gps.ts);
  }, [gps, tripOn, tripStart]);

  const trip = useMemo(() => {
    if (track.length < 2) return null;
    let km = 0;
    for (let i = 1; i < track.length; i++) {
      km += haversineKm(track[i - 1][0], track[i - 1][1], track[i][0], track[i][1]);
    }
    const durMin = tripStart ? Math.max(1, Math.round((track[track.length - 1][2] - tripStart) / 60000)) : null;
    return { nm: km / 1.852, pts: track.length, durMin };
  }, [track, tripStart]);

  // navigation origin: LIVE GPS when on, else the map's anchor point —
  // always labelled, never pretending to be the boat when it isn't.
  const origin = gps ? { lat: gps.lat, lon: gps.lon, live: true as const } : { lat, lon, live: false as const };

  const startNav = async (h: Hotspot) => {
    setNavTarget(h);
    setRoute(null);
    setRouteBusy(true);
    try {
      setRoute(await fetchRouteCheck(origin.lat, origin.lon, h.lat, h.lon));
    } catch (e) {
      setRoute(null);
    } finally {
      setRouteBusy(false);
    }
  };
  const stopNav = () => { setNavTarget(null); setRoute(null); };

  // live numbers, recomputed every GPS tick (client-side, offline-capable)
  const nav = useMemo(() => {
    if (!navTarget) return null;
    const dKm = haversineKm(origin.lat, origin.lon, navTarget.lat, navTarget.lon);
    const brg = bearingDeg(origin.lat, origin.lon, navTarget.lat, navTarget.lon);
    const spKn = gps?.speed != null && gps.speed >= 0 ? gps.speed * 1.943844 : null;
    const etaMin = spKn && spKn > 0.5 ? (dKm / 1.852 / spKn) * 60 : null;
    // course line = first leg of the verified route (or direct line)
    const a = route?.legs?.[0] ?? [origin.lat, origin.lon];
    const b = route?.legs?.[route.legs.length - 1] ?? [navTarget.lat, navTarget.lon];
    const xtkKm = haversineKm(a[0], a[1], b[0], b[1]) > 0.5
      ? crossTrackKm(origin.lat, origin.lon, a[0], a[1], b[0], b[1]) : 0;
    // real steering hint from the GPS's own heading (only while moving)
    let turn: { dir: string; deg: number } | null = null;
    if (gps?.heading != null && spKn != null && spKn > 1) {
      const dev = ((brg - gps.heading + 540) % 360) - 180; // signed -180..180
      if (Math.abs(dev) >= 8) turn = { dir: dev > 0 ? "RIGHT" : "LEFT", deg: Math.round(Math.abs(dev)) };
    }
    return { dNm: dKm / 1.852, brg, spKn, etaMin, xtkKm, turn, arrived: dKm / 1.852 < 0.3 };
  }, [navTarget, origin.lat, origin.lon, gps, route]);

  useEffect(() => {
    let alive = true;
    setErr(null); setData(null); setLayer("chl"); setView("map");
    fetchField(lat, lon)
      .then((j) => { if (alive) setData(j); })
      .catch((e) => {
        if (alive) setErr(lang === "hi"
          ? `फ़ील्ड डेटा नहीं आया — backend चल रहा है? (${e instanceof Error ? e.message : e})`
          : `Field data failed — is the backend running? (${e instanceof Error ? e.message : e})`);
      });
    return () => { alive = false; };
  }, [lat, lon, lang]);

  const active = LAYERS.find((l) => l.id === layer)!;
  const spots = useMemo(() => {
    if (!data) return [];
    return active.fromChl ? data.chl.points : data.met.points;
  }, [data, active]);

  const valOf = (p: FieldPoint): number | null | undefined => {
    switch (layer) {
      case "chl": return p.chl;
      case "wave": return p.wave_m;
      case "swell": return p.swell_m;
      case "wind": return p.gust_kn ?? p.wind_kn;
      case "current": return p.current_kn;
      case "sst": return p.sst_c;
    }
  };

  const has = (a?: (number | null)[]) => !!a && a.some((v) => v != null);

  return (
    <div className="fixed inset-0 z-[2000] bg-[#070D1A]/97 flex flex-col fade-up">
      {/* header */}
      <div className="shrink-0 flex items-start justify-between px-4 py-2.5 border-b border-[#16233C] gap-2">
        <div className="flex items-center gap-2.5 flex-wrap min-w-0">
          <h2 className="text-base font-bold text-white shrink-0">
            🔬 {lang === "hi" ? "विज़ुअल एक्सप्लोरर" : "Visual Explorer"}
          </h2>
          <span className="text-[11px] text-slate-500 font-mono shrink-0">{fmtLat(lat)}, {fmtLon(lon)} · ±1.2°</span>
          {!online && (
            <span className="text-[10px] rounded-md border border-red-500/50 bg-red-950/70 text-red-200 px-2 py-1 shrink-0">
              📡 {lang === "hi" ? "OFFLINE — GPS चलेगा; satellite/API data purana" : "OFFLINE — GPS works; API data is stale"}
            </span>
          )}
          {/* view toggle: 2D map vs living 3D ocean (same real data) */}
          <div className="flex gap-1 bg-[#0E1729] border border-[#1C2A45] rounded-lg p-1 shrink-0">
            <button
              onClick={() => setView("map")}
              className={`text-[11px] rounded-md px-2.5 py-1.5 transition ${
                view === "map" ? "bg-cyan-500/15 text-cyan-300 font-semibold" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              🗺️ {lang === "hi" ? "नक्शा" : "Map"}
            </button>
            <button
              onClick={() => setView("3d")}
              disabled={!data || !data.met.points.length}
              title={!data ? (lang === "hi" ? "पहले grid load होने दो" : "wait for the grid to load") : undefined}
              className={`text-[11px] rounded-md px-2.5 py-1.5 transition disabled:opacity-40 ${
                view === "3d" ? "bg-cyan-500/15 text-cyan-300 font-semibold" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              🌊 {lang === "hi" ? "3D समुद्र" : "3D Ocean"}
            </button>
          </div>
          {/* GPS + sea-marks toggles (map view) */}
          {view === "map" && (
            <>
              <button
                onClick={() => (gpsOn ? stopGps() : startGps())}
                title={lang === "hi"
                  ? "Phone/लैपटॉप का असली GPS (watchPosition) — boat के साथ blue dot चलेगा"
                  : "device's real GPS — the blue dot sails with you"}
                className={`text-[11px] rounded-md px-2.5 py-1.5 border transition shrink-0 ${
                  gpsOn
                    ? "bg-sky-500/20 text-sky-300 border-sky-400/50 font-semibold animate-pulse"
                    : "bg-[#0E1729] text-slate-300 border-[#1C2A45] hover:text-white"
                }`}
              >
                📍 {lang === "hi" ? (gpsOn ? "GPS चालू" : "Live GPS") : (gpsOn ? "GPS on" : "Live GPS")}
              </button>
              <button
                onClick={() => setSeaMarks((s) => !s)}
                title={lang === "hi"
                  ? "OpenSeaMap sea-marks layer: buoys/harbours/ channels — asli OSM nautical data"
                  : "OpenSeaMap sea-marks: buoys/harbours (real OSM nautical data)"}
                className={`text-[11px] rounded-md px-2.5 py-1.5 border transition shrink-0 ${
                  seaMarks
                    ? "bg-amber-500/20 text-amber-300 border-amber-400/50 font-semibold"
                    : "bg-[#0E1729] text-slate-300 border-[#1C2A45] hover:text-white"
                }`}
              >
                ⚓ {lang === "hi" ? "समुद्री निशान" : "Sea marks"}
              </button>
              <button
                onClick={() => {
                  if (tripOn) { setTripOn(false); }
                  else {
                    if (!gpsOn) startGps();          // trace needs real fixes
                    setTripOn(true);
                  }
                }}
                title={lang === "hi"
                  ? "Trip TRACE: boat jahan-jahan gayi, breadcrumb line banti jayegi (GPS fixes, refresh pe bhi saved)"
                  : "trip TRACE: breadcrumb line of where the boat really went (GPS fixes, refresh-safe)"}
                className={`text-[11px] rounded-md px-2.5 py-1.5 border transition shrink-0 ${
                  tripOn
                    ? "bg-orange-500/20 text-orange-300 border-orange-400/50 font-semibold animate-pulse"
                    : "bg-[#0E1729] text-slate-300 border-[#1C2A45] hover:text-white"
                }`}
              >
                🛤️ {lang === "hi" ? (tripOn ? "Trace चालू" : "Trip trace") : (tripOn ? "Tracing" : "Trip trace")}
              </button>
              <button
                onClick={() => setSos(true)}
                title={lang === "hi"
                  ? "SOS — बिना इंटरनेट काम करने वाला panel (GPS position, Coast Guard 1554, SMS, नज़दीकी बंदरगाह, VHF 16)"
                  : "SOS — works with zero internet (GPS position, Coast Guard 1554, SMS, nearest harbours, VHF 16)"}
                className="text-[11px] rounded-md px-2.5 py-1.5 border border-red-500/60 bg-red-500/15 text-red-300 font-bold transition shrink-0 hover:bg-red-500/30"
              >
                🆘 SOS
              </button>
            </>
          )}
          {/* layer switcher (map view) — wraps on small screens */}
          {view === "map" && (
            <div className="flex flex-wrap gap-1 bg-[#0E1729] border border-[#1C2A45] rounded-lg p-1">
              {LAYERS.map((l) => (
                <button
                  key={l.id}
                  onClick={() => setLayer(l.id)}
                  className={`text-[11px] rounded-md px-2.5 py-1.5 transition ${
                    layer === l.id ? "bg-cyan-500/15 text-cyan-300 font-semibold" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {lang === "hi" ? l.labelHi : l.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white text-xl leading-none px-2 py-1 shrink-0"
          aria-label="close"
        >
          ✕
        </button>
      </div>

      {/* body */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[2fr_1fr]">
        {/* map */}
        <div className="relative">
          {!data && !err && (
            <div className="absolute inset-0 flex items-center justify-center text-slate-200 text-sm z-[1001] bg-[#070D1A]/85 text-center px-6">
              ⏳ {lang === "hi"
                ? "असली ग्रिड सैंपल हो रहा है… (NOAA satellite + Open-Meteo models — पहली बार 15-30 सेकंड लग सकते हैं)"
                : "Sampling the real grid… (NOAA satellite + Open-Meteo models — first load can take 15-30 s)"}
            </div>
          )}
          {err && (
            <div className="absolute inset-0 flex items-center justify-center text-red-300 text-sm z-[1001] px-6 text-center">{err}</div>
          )}
          {view === "3d" && data ? (
            <Ocean3D key={`${lat}:${lon}:${data.generated_at}`} data={data} lang={lang} />
          ) : (
          <>
          <MapContainer center={[lat, lon]} zoom={9} style={{ height: "100%", width: "100%", background: "#070D1A" }}>
            <TileLayer
              attribution="&copy; OpenStreetMap contributors"
              url="/api/v1/tiles/{z}/{x}/{y}.png"
            />
            {/* center point */}
            <CircleMarker center={[lat, lon]} radius={8}
              pathOptions={{ color: "#0ea5e9", weight: 3, fillColor: "#22d3ee", fillOpacity: 0.55 }}>
              <Tooltip permanent direction="top" offset={[0, -10]}>📍 {lang === "hi" ? "आपका बिंदु" : "Your point"}</Tooltip>
            </CircleMarker>
            {/* hotspot lines (chl layer) */}
            {layer === "chl" && data?.hotspots.map((h, i) => (
              <Polyline key={`hs-${i}`} positions={[[lat, lon], [h.lat, h.lon]]}
                pathOptions={{ color: "#059669", weight: 2, dashArray: "5 6", opacity: 0.75 }} />
            ))}
            {/* OpenSeaMap sea-marks (real nautical OSM data: buoys, harbours) */}
            {seaMarks && (
              <TileLayer
                attribution="&copy; OpenSeaMap contributors"
                url="/api/v1/seamarks/{z}/{x}/{y}.png"
                opacity={0.95}
              />
            )}
            {/* trip TRACE: breadcrumb line of real GPS fixes */}
            {track.length > 1 && (
              <Polyline
                positions={track.map((p) => [p[0], p[1]] as [number, number])}
                pathOptions={{ color: "#fb923c", weight: 3, opacity: 0.85 }}
              />
            )}
            {/* live GPS fix: blue dot + REAL accuracy radius (meters) */}
            {gps && (
              <>
                <Circle center={[gps.lat, gps.lon]} radius={gps.acc}
                  pathOptions={{ color: "#38bdf8", weight: 1, fillColor: "#38bdf8", fillOpacity: 0.12 }} />
                <CircleMarker center={[gps.lat, gps.lon]} radius={7}
                  pathOptions={{ color: "#0c4a6e", weight: 2, fillColor: "#38bdf8", fillOpacity: 1 }}>
                  <Tooltip permanent direction="top" offset={[0, -8]}>
                    🚤 {lang === "hi" ? `आप (live GPS ±${Math.round(gps.acc)}m)` : `you (live GPS ±${Math.round(gps.acc)}m)`}
                  </Tooltip>
                </CircleMarker>
              </>
            )}
            {/* verified course line to the nav target (backend GLOBE mask) */}
            {navTarget && route && (
              <Polyline
                positions={route.legs.map((p) => [p[0], p[1]] as [number, number])}
                pathOptions={{
                  color: route.ok === false ? "#ef4444" : route.ok === null ? "#f59e0b" : "#22d3ee",
                  weight: 4, opacity: 0.9,
                  dashArray: route.ok === false ? "4 6" : undefined,
                }}
              />
            )}
            {navTarget && (
              <CircleMarker center={[navTarget.lat, navTarget.lon]} radius={10}
                pathOptions={{ color: "#f59e0b", weight: 3, fillColor: "#f59e0b", fillOpacity: 0.35 }}>
                <Tooltip permanent direction="top" offset={[0, -10]}>
                  🎯 {lang === "hi" ? "लक्ष्य" : "target"} · {navTarget.chl} mg/m³
                </Tooltip>
              </CircleMarker>
            )}
            {/* data spots */}
            {spots.map((p, i) => {
              const v = valOf(p);
              if (v == null) return null;
              const color = active.color(v as number);
              const isHot = layer === "chl" && data?.hotspots.some((h) => h.lat === p.lat && h.lon === p.lon);
              return (
                <CircleMarker
                  key={`${layer}-sp-${i}`}
                  center={[p.lat, p.lon]}
                  radius={active.radius(v as number)}
                  pathOptions={{
                    color: "#0B1322", weight: isHot ? 3 : 1,
                    fillColor: color, fillOpacity: isHot ? 0.95 : 0.78,
                  }}
                >
                  <Tooltip>
                    <div className="text-xs">
                      <strong>{fmtLat(p.lat)}, {fmtLon(p.lon)}</strong><br />
                      {p.chl != null && <>🎣 chl: <b>{p.chl}</b> mg/m³<br /></>}
                      {p.wave_m != null && <>🌊 waves: <b>{p.wave_m}</b> m · swell {p.swell_m ?? "—"} m<br /></>}
                      {p.wind_kn != null && <>💨 wind: <b>{p.wind_kn}</b> kn · gusts <b>{p.gust_kn ?? "—"}</b> kn<br /></>}
                      {p.current_kn != null && <>🌀 current: <b>{p.current_kn}</b> kn<br /></>}
                      {p.sst_c != null && <>🌡️ SST: <b>{p.sst_c}</b> °C</>}
                    </div>
                  </Tooltip>
                </CircleMarker>
              );
            })}
          </MapContainer>
          {/* legend */}
          <div className="absolute bottom-3 left-3 z-[1000] surface-2 px-3 py-2 text-[10px] text-slate-300 space-y-1 max-w-[320px]">
            <div className="font-semibold text-slate-100">
              {lang === "hi" ? active.labelHi : active.label} ({active.unit})
            </div>
            <div>{lang === "hi" ? active.legendHi : active.legend}</div>
            {layer === "chl" && (
              <div className="text-slate-500">{lang === "hi" ? "ज़्यादा chl = ज़्यादा प्लांक्टन = मछली का खाना" : "more chl = more plankton = fish food"}</div>
            )}
          </div>

          {/* GPS status (honest errors — browser rule, permission, etc.) */}
          {gpsErr && (
            <div className="absolute top-3 left-3 z-[1000] max-w-[340px] rounded-lg border border-red-400/40 bg-red-950/90 px-3 py-2 text-[11px] text-red-200">
              {gpsErr}
            </div>
          )}

          {/* trip TRACE stats chip (bottom-right, refresh-safe record) */}
          {trip && (
            <div className="absolute bottom-3 right-3 z-[1000] surface-2 px-3 py-2 text-[10px] text-slate-300 space-y-0.5 max-w-[240px]">
              <div className="font-semibold text-orange-300">
                🛤️ {lang === "hi" ? "trip trace" : "trip trace"} {tripOn ? (lang === "hi" ? "(record हो रहा)" : "(recording)") : (lang === "hi" ? "(saved)" : "(saved)")}
              </div>
              <div>
                {trip.nm.toFixed(1)} NM · {trip.pts} GPS fixes
                {trip.durMin != null && (
                  <> · {trip.durMin >= 60 ? `${Math.floor(trip.durMin / 60)}h ${trip.durMin % 60}m` : `${trip.durMin} min`}</>
                )}
              </div>
              <button onClick={clearTrip} className="text-red-300/80 hover:text-red-200 underline">
                {lang === "hi" ? "trace मिटाओ" : "clear trace"}
              </button>
            </div>
          )}

          {/* 🧭 NAVIGATION HUD — real marine guidance: course line,
              distance/bearing/ETA from the device's OWN position. */}
          {navTarget && nav && (
            <div className="absolute top-3 left-3 z-[1000] w-[300px] rounded-xl border border-cyan-400/40 bg-[#081120]/95 px-3.5 py-3 text-[12px] shadow-2xl space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="font-bold text-cyan-300">
                  🧭 {lang === "hi" ? "नेविगेशन चालू" : "NAVIGATION ON"}
                </div>
                <button onClick={stopNav} className="text-slate-500 hover:text-white text-sm px-1" aria-label="stop nav">✕</button>
              </div>
              <div className="text-slate-400 text-[10.5px]">
                {origin.live
                  ? (lang === "hi" ? `📍 origin: LIVE GPS (±${Math.round(gps?.acc ?? 0)}m)` : `📍 origin: LIVE GPS (±${Math.round(gps?.acc ?? 0)}m)`)
                  : (lang === "hi" ? "📍 origin: मैप बिंदु (GPS बंद — manual anchor)" : "📍 origin: map point (GPS off — manual anchor)")}
              </div>
              <div className="text-slate-200">
                🎯 {fmtLat(navTarget.lat)}, {fmtLon(navTarget.lon)} · <b className="text-emerald-300">{navTarget.chl}</b> mg/m³
              </div>
              <div className="grid grid-cols-2 gap-1.5 text-center pt-1">
                <div className="rounded bg-[#0E1B30] py-1.5">
                  <div className="text-[9px] text-slate-500">{lang === "hi" ? "दूरी" : "distance"}</div>
                  <div className="font-bold text-cyan-200">{nav.dNm.toFixed(1)} NM</div>
                </div>
                <div className="rounded bg-[#0E1B30] py-1.5">
                  <div className="text-[9px] text-slate-500">{lang === "hi" ? "दिशा" : "course"}</div>
                  <div className="font-bold text-cyan-200">{Math.round(nav.brg)}° {compass(nav.brg)}</div>
                </div>
                <div className="rounded bg-[#0E1B30] py-1.5">
                  <div className="text-[9px] text-slate-500">{lang === "hi" ? "रफ़्तार (GPS)" : "speed (GPS)"}</div>
                  <div className="font-bold text-cyan-200">
                    {nav.spKn != null ? `${nav.spKn.toFixed(1)} kn` : (lang === "hi" ? "— (GPS speed n/a)" : "— (n/a)")}
                  </div>
                </div>
                <div className="rounded bg-[#0E1B30] py-1.5">
                  <div className="text-[9px] text-slate-500">ETA</div>
                  <div className="font-bold text-cyan-200">
                    {nav.etaMin != null
                      ? nav.etaMin >= 60 ? `${Math.floor(nav.etaMin / 60)}h ${Math.round(nav.etaMin % 60)}m` : `${Math.round(nav.etaMin)} min`
                      : (lang === "hi" ? "— (boat रुकी / speed n/a)" : "— (no speed)")}
                  </div>
                </div>
              </div>
              {/* route-verification line — never a fake 'safe' */}
              <div className={`rounded px-2 py-1.5 text-[10.5px] ${
                routeBusy ? "bg-[#0E1B30] text-slate-400"
                : route?.ok === true ? "bg-emerald-950/70 text-emerald-200 border border-emerald-500/30"
                : route?.ok === false ? "bg-red-950/70 text-red-200 border border-red-500/30"
                : route?.ok === null ? "bg-amber-950/70 text-amber-200 border border-amber-500/30"
                : "bg-[#0E1B30] text-slate-400"}`}>
                {routeBusy && (lang === "hi" ? "🛰️ रास्ता verify हो रहा है (GLOBE 1km mask)…" : "🛰️ verifying course (GLOBE 1 km mask)…")}
                {!routeBusy && route?.ok === true && (route.detour
                  ? `🛟 ${lang === "hi" ? "सीधा रास्ता ज़मीन से गुज़रता है — detour waypoint बना दिया" : "direct crosses land — detour waypoint computed"} (GLOBE ✓)`
                  : `🛟 ${lang === "hi" ? "सीधा रास्ता पूरा पानी है" : "straight course is all water"} (GLOBE ✓)`)}
                {!routeBusy && route?.ok === false && `⛔ ${lang === "hi" ? "रास्ता ज़मीन से गुज़रता है — BLOCKED, fake line नहीं दिखाई" : "course crosses land — BLOCKED, no fake line drawn"}`}
                {!routeBusy && route?.ok === null && `⚠️ ${lang === "hi" ? "UNVERIFIED — land mask उपलब्ध नहीं; सावधानी से जाएं" : "UNVERIFIED — land mask unavailable"}`}
                {!routeBusy && !route && (lang === "hi" ? "route check fail — network?" : "route check failed — network?")}
              </div>
              {/* steering hint from the GPS's own heading (while moving) */}
              {!nav.arrived && nav.turn && (
                <div className="rounded bg-cyan-500/15 border border-cyan-400/40 px-2 py-1.5 text-cyan-100 font-bold text-center">
                  {nav.turn.dir === "RIGHT" ? "↱" : "↰"} {nav.turn.deg}° {lang === "hi"
                    ? (nav.turn.dir === "RIGHT" ? "दाएं घुड़ो" : "बाएं घुड़ो")
                    : `turn ${nav.turn.dir.toLowerCase()}`}
                  <span className="font-normal text-[10px] text-slate-400"> · GPS heading vs course</span>
                </div>
              )}
              {/* arrival + off-course — real guidance moments */}
              {nav.arrived ? (
                <div className="rounded bg-emerald-500/20 border border-emerald-400/50 px-2 py-1.5 text-emerald-200 font-bold text-center">
                  🎉 {lang === "hi" ? "चुने हुए क्लोरोफिल बिंदु पर पहुंच गए" : "ARRIVED at the selected chlorophyll observation"}
                </div>
              ) : nav.xtkKm > 0.9 ? (
                <div className="rounded bg-amber-500/15 border border-amber-400/40 px-2 py-1.5 text-amber-200 text-center">
                  ⚠️ {lang === "hi" ? `course से ${(nav.xtkKm / 1.852).toFixed(1)} NM हटे — ${Math.round(nav.brg)}° ${compass(nav.brg)} पकड़ो` : `${(nav.xtkKm / 1.852).toFixed(1)} NM off course — steer ${Math.round(nav.brg)}°`}
                </div>
              ) : null}
              <div className="text-[9.5px] text-slate-500">
                {lang === "hi"
                  ? "Course-line guidance (समुद्र में roads नहीं होते) — असली marine GPS भी यही देता है। Buoy/ชैनल के लिए ⚓ layer चालू करो।"
                  : "Course-line guidance (no roads at sea) — real marine GPS works the same. Enable ⚓ for buoys/channels."}
              </div>
            </div>
          )}
          </>
          )}
          {/* 🆘 zero-internet emergency panel (fully client-side) */}
          {sos && (
            <SosPanel
              lat={lat} lon={lon}
              gps={gps} gpsOn={gpsOn} online={online}
              lang={lang}
              onClose={() => setSos(false)}
              onStartGps={startGps}
            />
          )}
        </div>

        {/* right panel */}
        <div className="border-l border-[#16233C] overflow-y-auto p-4 space-y-4 bg-[#0A1120]">
          {/* Legacy API `hotspots`: high observed chlorophyll cells only. */}
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300/90 mb-2">
              🛰️ {lang === "hi" ? "ऊँचे क्लोरोफिल बिंदु" : "Highest chlorophyll cells"}
              {data?.chl.date ? <span className="text-slate-600 normal-case font-normal"> · NOAA {data.chl.date}</span> : ""}
            </div>
            <div className="mb-2 text-[10px] leading-snug text-slate-500">
              {lang === "hi"
                ? "केवल मापा गया क्लोरोफिल क्रम; यह PFZ, मछली, पकड़ या HAB सलाह नहीं है।"
                : "Observed chlorophyll ranking only — not a PFZ, fish/catch estimate, HAB diagnosis, or recommendation."}
            </div>
            {!data ? (
              <div className="text-xs text-slate-500">…</div>
            ) : data.hotspots.length === 0 ? (
              <div className="text-xs text-slate-500">
                {lang === "hi" ? "इस ग्रिड में chl डेटा नहीं (बादल/सीमा) — नीचे असली कारण देखें।" : "No chl data in this grid (clouds/edge) — real reason below."}
                {data.chl.error && <div className="mt-1 text-red-400/80">chlorophyll: {data.chl.error}</div>}
              </div>
            ) : (
              <ul className="space-y-1.5">
                {data.hotspots.map((h, i) => (
                  <li key={i} className="surface px-3 py-2 text-xs space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-slate-200 font-medium">
                        #{i + 1} · {fmtLat(h.lat)}, {fmtLon(h.lon)}
                      </span>
                      <span className="text-slate-400 text-right">
                        <b className="text-emerald-300">{h.chl}</b> mg/m³<br />
                        {h.distance_nm} NM {h.bearing}
                      </span>
                      <button
                        onClick={() => startNav(h)}
                        title={lang === "hi"
                          ? "इस माप बिंदु तक रास्ता जाँचें (मछली सलाह नहीं)"
                          : "check a course to this observation (not fishing advice)"}
                        className={`shrink-0 rounded-md border px-2 py-1 text-[11px] transition ${
                          navTarget === h
                            ? "bg-cyan-500/20 border-cyan-400/60 text-cyan-300 font-semibold"
                            : "border-[#24405f] text-cyan-300/80 hover:bg-cyan-500/10"
                        }`}
                      >
                        🧭 {lang === "hi" ? "रास्ता" : "route"}
                      </button>
                    </div>
                    {/* display-band and coastal retrieval-quality context */}
                    <div className="text-[10px] text-slate-500">
                      {h.bloom ? "high-chl display band (not HAB)" : "lower-chl display band"}
                      {h.coast_km != null ? ` · ${lang === "hi" ? "तट से" : "coast"} ~${Math.round(h.coast_km)} km` : ""}
                    </div>
                    {h.caveat && (
                      <div className="text-[10px] leading-snug text-amber-300/90 border border-amber-500/30 bg-amber-950/40 rounded px-2 py-1">
                        ⚠️ {h.caveat}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 48 h evidence charts (same arrays as the verdict) */}
          {trend && trend.labels.length > 1 && (
            <div className="space-y-3">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                📈 {lang === "hi" ? "आपके बिंदु का ट्रेंड (48 घंटे)" : "Your point — 48 h trend"}
              </div>
              <div className="surface p-3">
                <div className="text-[10px] text-slate-500 mb-1">🌊 {lang === "hi" ? "लहरें + swell (m)" : "Waves + swell (m)"}</div>
                <LineChart
                  labels={trend.labels} unit=" m"
                  series={[
                    { label: lang === "hi" ? "लहरें" : "waves", values: trend.wave_m, color: "#22d3ee" },
                    ...(has(trend.swell_m) ? [{ label: "swell", values: trend.swell_m!, color: "#818cf8", dashed: true }] : []),
                  ]}
                  thresholds={[
                    { value: 2.5, color: "#f59e0b", label: "2.5" },
                    { value: 4, color: "#ef4444", label: "4" },
                  ]}
                />
              </div>
              <div className="surface p-3">
                <div className="text-[10px] text-slate-500 mb-1">💨 {lang === "hi" ? "हवा + gusts (kn)" : "Wind + gusts (kn)"}</div>
                <LineChart
                  labels={trend.labels} unit=" kn"
                  series={[
                    { label: lang === "hi" ? "हवा" : "wind", values: trend.wind_kn, color: "#a78bfa" },
                    { label: "gusts", values: trend.gust_kn, color: "#f472b6", dashed: true },
                  ]}
                  thresholds={[
                    { value: 20, color: "#f59e0b", label: "20" },
                    { value: 34, color: "#ef4444", label: "34" },
                  ]}
                />
              </div>
              {has(trend.current_kn) && (
                <div className="surface p-3">
                  <div className="text-[10px] text-slate-500 mb-1">🌀 {lang === "hi" ? "धारा (kn)" : "Current (kn)"}</div>
                  <LineChart
                    labels={trend.labels} unit=" kn"
                    series={[{ label: "current", values: trend.current_kn!, color: "#34d399" }]}
                    thresholds={[{ value: 3, color: "#f59e0b", label: "3" }]}
                  />
                </div>
              )}
              {has(trend.sst_c) && (
                <div className="surface p-3">
                  <div className="text-[10px] text-slate-500 mb-1">🌡️ SST (°C)</div>
                  <LineChart
                    labels={trend.labels} unit="°C"
                    series={[{ label: "SST", values: trend.sst_c!, color: "#fbbf24" }]}
                  />
                </div>
              )}
            </div>
          )}

          {/* data provenance */}
          {data && (
            <div className="surface p-3 text-[10px] text-slate-500 space-y-1">
              <div><span className="text-slate-300 font-semibold">chlorophyll:</span> {data.chl.source ?? "—"}{data.chl.error ? ` · ⚠️ ${data.chl.error}` : ` · ${data.chl.n} cells`}</div>
              <div><span className="text-slate-300 font-semibold">waves/wind/current/SST:</span> {data.met.source ?? "—"}{data.met.error ? ` · ⚠️ ${data.met.error}` : ` · ${data.met.n} cells`}</div>
              <div className="italic pt-1">{data.note}</div>
              <div>generated: {new Date(data.generated_at).toLocaleString()}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
