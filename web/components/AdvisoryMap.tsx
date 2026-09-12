"use client";

/**
 * Mini map for the advisory card — where am I, and which way is the
 * official INCOIS PFZ? Read-only, single-purpose, no zone clutter.
 * PFZ direction comes from the advisory's real bearing+distance.
 * Basemap = real OpenStreetMap tiles (same as the main map tab) —
 * CARTO dark tiles started serving "API KEY REQUIRED" watermarks.
 */
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";

const COMPASS_DEG: Record<string, number> = {
  N: 0, NNE: 22.5, NE: 45, ENE: 67.5, E: 90, ESE: 112.5, SE: 135, SSE: 157.5,
  S: 180, SSW: 202.5, SW: 225, WSW: 247.5, W: 270, WNW: 292.5, NW: 315, NNW: 337.5,
};

function destination(lat: number, lon: number, bearingDeg: number, distKm: number): [number, number] {
  const rad = (bearingDeg * Math.PI) / 180;
  const dLat = (distKm * Math.cos(rad)) / 111.0;
  const dLon = (distKm * Math.sin(rad)) / (111.0 * Math.cos((lat * Math.PI) / 180));
  return [lat + dLat, lon + dLon];
}

export default function AdvisoryMap({
  lat,
  lon,
  pfzNm,
  pfzBearing,
  lang,
}: {
  lat: number;
  lon: number;
  pfzNm?: number | null;
  pfzBearing?: string | null;
  lang: "hi" | "en";
}) {
  const hasPfz = pfzNm != null && pfzBearing != null && COMPASS_DEG[pfzBearing] != null;
  const pfzPoint = hasPfz ? destination(lat, lon, COMPASS_DEG[pfzBearing], pfzNm! * 1.852) : null;
  const mid: [number, number] = pfzPoint
    ? [(lat + pfzPoint[0]) / 2, (lon + pfzPoint[1]) / 2]
    : [lat, lon];

  return (
    <div className="rounded-lg overflow-hidden border border-[#1C2A45]">
      <MapContainer
        center={mid}
        zoom={hasPfz ? 7 : 8}
        style={{ height: 220, width: "100%", background: "#0A1120" }}
        zoomControl={false}
        dragging={false}
        scrollWheelZoom={false}
        doubleClickZoom={false}
        boxZoom={false}
        keyboard={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="/api/v1/tiles/{z}/{x}/{y}.png"
        />
        {/* you are here — pulsing cyan target */}
        <CircleMarker center={[lat, lon]} radius={8}
          pathOptions={{ color: "#22d3ee", weight: 2.5, fillColor: "#22d3ee", fillOpacity: 0.35 }}>
          <Tooltip permanent direction="top" offset={[0, -10]} className="advisory-mini-tip">
            {lang === "hi" ? "📍 आप यहाँ" : "📍 You are here"}
          </Tooltip>
        </CircleMarker>
        <CircleMarker center={[lat, lon]} radius={16}
          pathOptions={{ color: "#22d3ee", weight: 1, dashArray: "3 3", fillOpacity: 0, opacity: 0.5 }} />
        {/* PFZ direction */}
        {pfzPoint && (
          <>
            <Polyline positions={[[lat, lon], pfzPoint]}
              pathOptions={{ color: "#34d399", weight: 2, dashArray: "6 6" }} />
            <CircleMarker center={pfzPoint} radius={7}
              pathOptions={{ color: "#34d399", weight: 2, fillColor: "#34d399", fillOpacity: 0.3 }}>
              <Tooltip permanent direction="top" offset={[0, -8]} className="advisory-mini-tip">
                🎣 PFZ · {pfzNm} NM
              </Tooltip>
            </CircleMarker>
          </>
        )}
      </MapContainer>
    </div>
  );
}
