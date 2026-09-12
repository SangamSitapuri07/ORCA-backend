"use client";

/** Route map for the Voyage Planner lab.
 *  - legs polyline (land-verified course from the backend; amber dashed
 *    straight line while only start/dest are known)
 *  - numbered per-sample markers, coloured by their REAL state —
 *    every colour is evidence from the route-advisory, never cosmetic
 *  - voyage recommendation badges (P = official INCOIS PFZ line point,
 *    official INCOIS PFZ candidate) — popup carries name/NM/experimental ordering
 *  - click-to-pick start/destination when a pick mode is armed */

import { useEffect, useMemo } from "react";
import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  CircleMarker,
  Popup,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  PointState,
  RouteAdvisoryPoint,
  VoyageReco,
  fmtLat,
  fmtLon,
} from "@/lib/orca-client";

export type LL = { lat: number; lon: number };

export const STATE_COLOR: Record<PointState, string> = {
  good: "#16a34a",
  caution: "#d97706",
  danger: "#dc2626",
  unknown: "#64748b",
};

/** 1-decimal knots truth (B10a — raw 19.6 must not display as "20" next to the ≥20 rule) */
const fmtKn = (v: number) => {
  const r = Math.round(v * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
};

function badge(html: string, bg: string, size = 26): L.DivIcon {
  return L.divIcon({
    className: "",
    html:
      `<div style="width:${size}px;height:${size}px;border-radius:9px;background:${bg};` +
      `border:2px solid rgba(255,255,255,.92);display:flex;align-items:center;justify-content:center;` +
      `color:#fff;font-weight:800;font-size:11px;font-family:system-ui,sans-serif;` +
      `box-shadow:0 3px 10px rgba(0,0,0,.45)">${html}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function FitView({
  start,
  dest,
  legs,
}: {
  start: LL | null;
  dest: LL | null;
  legs: [number, number][] | null;
}) {
  const map = useMap();
  const key = useMemo(
    () => JSON.stringify({ start, dest, legs }),
    [start, dest, legs]
  );
  useEffect(() => {
    const pts: [number, number][] =
      legs && legs.length > 1
        ? legs
        : ([start, dest].filter(Boolean) as LL[]).map((p) => [p.lat, p.lon]);
    if (pts.length >= 2) {
      map.fitBounds(L.latLngBounds(pts.map((p) => L.latLng(p[0], p[1]))), {
        padding: [30, 30],
      });
    } else if (pts.length === 1) {
      map.flyTo(pts[0], 8, { duration: 0.8 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map]);
  return null;
}

function MapClick({
  armed,
  onPick,
}: {
  armed: boolean;
  onPick: (lat: number, lon: number) => void;
}) {
  useMapEvents({
    click(e) {
      if (armed) onPick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export default function RouteMap({
  start,
  dest,
  legs,
  points,
  recos,
  pickArmed,
  onPick,
}: {
  start: LL | null;
  dest: LL | null;
  legs: [number, number][] | null;
  points: RouteAdvisoryPoint[];
  recos: VoyageReco[];
  /** true = the next map click fills whichever pick mode is armed */
  pickArmed: boolean;
  onPick: (lat: number, lon: number) => void;
}) {
  const straight: [number, number][] | null =
    start && dest
      ? [
          [start.lat, start.lon],
          [dest.lat, dest.lon],
        ]
      : null;

  return (
    <MapContainer
      center={[19.5, 74.0]}
      zoom={5}
      style={{ height: "100%", width: "100%", background: "#0A1120" }}
      zoomControl={true}
    >
      <TileLayer
        url="/api/v1/tiles/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />
      <MapClick armed={pickArmed} onPick={onPick} />
      <FitView start={start} dest={dest} legs={legs} />

      {/* direct course — solid reference only when nothing computed yet;
          on a REROUTED path it stays dashed-VISIBLE so the contrast
          "blocked line over land vs verified sea path" is on the map */}
      {straight && (!legs || legs.length > 2) && (
        <Polyline
          positions={straight}
          pathOptions={{ color: "#d97706", weight: 2, dashArray: "6 8", opacity: 0.8 }}
        >
          {legs && legs.length > 2 && (
            <Popup>direct course — crosses LAND (blocked); cyan line is the verified sea path</Popup>
          )}
        </Polyline>
      )}
      {/* land-verified course from the backend */}
      {legs && legs.length > 1 && (
        <Polyline
          positions={legs}
          pathOptions={{ color: "#38bdf8", weight: 4, opacity: 0.95 }}
        />
      )}
      {/* sea-path waypoints (middle vertices of a rerouted course) */}
      {legs && legs.length > 2 &&
        legs.slice(1, -1).map((w, i) => (
          <CircleMarker
            key={`wp-${i}`}
            center={[w[0], w[1]]}
            radius={5}
            pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: "#7dd3fc", fillOpacity: 1 }}
          >
            <Popup>
              waypoint {i + 1} — {fmtLat(w[0])} {fmtLon(w[1])}
              <br />
              <i>ocean path pivot, verified at 1 km</i>
            </Popup>
          </CircleMarker>
        ))}

      {start && (
        <Marker position={[start.lat, start.lon]} icon={badge("S", "#0d9488")}>
          <Popup>
            START — {fmtLat(start.lat)} {fmtLon(start.lon)}
          </Popup>
        </Marker>
      )}
      {dest && (
        <Marker position={[dest.lat, dest.lon]} icon={badge("D", "#be185d")}>
          <Popup>
            DESTINATION — {fmtLat(dest.lat)} {fmtLon(dest.lon)}
          </Popup>
        </Marker>
      )}

      {/* numbered evidence points along the verified course */}
      {points.map((p, i) => (
        <Marker
          key={`pt-${i}`}
          position={[p.lat, p.lon]}
          icon={badge(String(i + 1), STATE_COLOR[p.state] ?? "#64748b", 24)}
        >
          <Popup>
            <div style={{ fontSize: 12 }}>
              <b>
                Point {i + 1}
                {p.vertex ? " · vertex" : ""} — {p.state.toUpperCase()}
              </b>
              <br />
              {fmtLat(p.lat)} {fmtLon(p.lon)} · sailed {(p.sail_km / 1.852).toFixed(1)} NM
              {p.wave_m != null && (
                <>
                  <br />wave {p.wave_m.toFixed(1)} m
                  {p.wave_48h_max_m != null && ` (48h max ${p.wave_48h_max_m.toFixed(1)} m)`}
                </>
              )}
              {p.wind_48h_max_kn != null && <><br />wind 48h max {fmtKn(p.wind_48h_max_kn)} kn</>}
              {p.gust_48h_max_kn != null && <><br />gust 48h max {fmtKn(p.gust_48h_max_kn)} kn</>}
              {p.current_kn != null && <><br />current {p.current_kn.toFixed(2)} kn</>}
              {p.sst_c != null && <><br />SST {p.sst_c.toFixed(1)} °C</>}
              {(p.why || p.note) && <><br /><i>{p.why ?? p.note}</i></>}
            </div>
          </Popup>
        </Marker>
      ))}

      {/* voyage candidates — official INCOIS PFZ geometry only */}
      {recos.map((r, i) => (
        <Marker
          key={`reco-${i}`}
          position={[r.lat, r.lon]}
          icon={badge(
            `${i + 1}`,
            r.kind === "pfz" ? "#0d9488" : "#7c3aed",
            28
          )}
        >
          <Popup>
            <div style={{ fontSize: 12, maxWidth: 220 }}>
              <b>
                #{i + 1} — Official INCOIS PFZ candidate
              </b>
              <br />
              {r.name}
              <br />
              {r.distance_nm.toFixed(1)} NM · score <b>{r.score}</b> · state {r.state}
              {r.wave_m != null && <><br />wave {r.wave_m.toFixed(1)} m</>}
              {r.sst_c != null && <><br />SST {r.sst_c.toFixed(1)} °C</>}
            </div>
          </Popup>
        </Marker>
      ))}

      {pickArmed && (
        <div className="leaflet-top leaflet-right">
          <div className="leaflet-control bg-[#0E1729]/95 border border-cyan-400/40 text-cyan-200 rounded-lg shadow-xl px-3 py-2 m-2 text-xs font-semibold backdrop-blur">
            Click on the map to set the point
          </div>
        </div>
      )}
    </MapContainer>
  );
}
