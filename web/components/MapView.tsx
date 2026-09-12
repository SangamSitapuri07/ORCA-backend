"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  MapContainer, TileLayer, Marker, Popup, GeoJSON,
  CircleMarker, useMap, useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { DemoZone, fetchLayers, LayersResponse } from "@/lib/orca-client";
import { t, Lang } from "@/lib/i18n";

// Fix broken default marker icons under webpack (classic Leaflet quirk)
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "/leaflet/marker-icon-2x.png",
  iconUrl: "/leaflet/marker-icon.png",
  shadowUrl: "/leaflet/marker-shadow.png",
});

const LAYER_STYLES: Record<string, L.PathOptions> = {
  official_pfz: { color: "#16a34a", weight: 3, dashArray: "8 6", opacity: 0.9 },
  cyclone_radius: { color: "#ea580c", weight: 2, dashArray: "4 6", fillColor: "#ea580c", fillOpacity: 0.12 },
  eez: { color: "#7c3aed", weight: 1.5, dashArray: "2 4", fillOpacity: 0.03 },
};

function FlyToSelected({ selected }: { selected: DemoZone | null }) {
  const map = useMap();
  useEffect(() => {
    if (selected) map.flyTo([selected.lat, selected.lon], 6, { duration: 1.2 });
  }, [selected, map]);
  return null;
}

function ClickToAnalyze({ onClick }: { onClick: (lat: number, lon: number) => void }) {
  useMapEvents({
    // Normal left-click anywhere on the ocean -> analyse that exact point.
    // Leaflet only fires "click" for a short press (no drag), so panning
    // never triggers an accidental analysis. Right-click kept as alias.
    click(e) {
      onClick(e.latlng.lat, e.latlng.lng);
    },
    contextmenu(e) {
      onClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export default function MapView({
  zones,
  selected,
  onSelect,
  lang,
}: {
  zones: DemoZone[];
  selected: DemoZone | null;
  onSelect: (zone: DemoZone) => void;
  lang: Lang;
}) {
  const [layers, setLayers] = useState<LayersResponse | null>(null);
  const [enabled, setEnabled] = useState<Record<string, boolean>>({
    official_pfz: true, cyclone: true, port: true, eez: false,
  });
  const [layersErr, setLayersErr] = useState<string | null>(null);

  const loadLayers = useCallback(async () => {
    try {
      setLayersErr(null);
      const all = await fetchLayers(["official_pfz", "cyclone", "port"]);
      // EEZ polygon is heavy — fetch only when enabled
      if (enabled.eez) {
        try {
          const eez = await fetchLayers(["eez"]);
          setLayers({ ...all, features: [...all.features, ...eez.features] });
          return;
        } catch { /* eez optional */ }
      }
      setLayers(all);
    } catch (e) {
      setLayersErr(e instanceof Error ? e.message.slice(0, 120) : "layers failed");
    }
  }, [enabled.eez]);

  useEffect(() => { loadLayers(); }, [loadLayers]);

  const features = useMemo(() => {
    if (!layers) return [];
    return layers.features.filter((f: any) => {
      const k = f.properties?.layer;
      if (k === "official_pfz") return enabled.official_pfz;
      if (k === "cyclone" || k === "cyclone_radius") return enabled.cyclone;
      if (k === "port") return enabled.port;
      if (k === "eez") return enabled.eez;
      return true;
    });
  }, [layers, enabled]);

  const lineFeatures = useMemo(
    () => features.filter((f: any) => f.geometry?.type !== "Point"),
    [features]
  );
  const pointFeatures = useMemo(
    () => features.filter((f: any) => f.geometry?.type === "Point"),
    [features]
  );

  const geoJsonData = useMemo(
    () => ({ type: "FeatureCollection" as const, features: lineFeatures }),
    [lineFeatures]
  );

  const handleMapClick = (lat: number, lon: number) => {
    let nearest = zones[0];
    let minDist = Infinity;
    for (const z of zones) {
      const d = Math.hypot(z.lat - lat, z.lon - lon);
      if (d < minDist) { minDist = d; nearest = z; }
    }
    onSelect({
      name: minDist < 3
        ? `${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E (near ${nearest.name})`
        : `Custom: ${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`,
      lat, lon,
    });
  };

  const locateMe = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => onSelect({
        name: `📍 ${t(lang, "my_location")} (${pos.coords.latitude.toFixed(2)}°N, ${pos.coords.longitude.toFixed(2)}°E)`,
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
      }),
      (err) => alert(`Geolocation failed: ${err.message}`),
      { enableHighAccuracy: false, timeout: 8000 }
    );
  };

  const LAYER_KEYS: { key: string; label: string }[] = [
    { key: "official_pfz", label: t(lang, "layer_pfz") },
    { key: "cyclone", label: t(lang, "layer_cyclone") },
    { key: "port", label: t(lang, "layer_ports") },
    { key: "eez", label: t(lang, "layer_eez") },
  ];

  return (
    <MapContainer center={[15, 78]} zoom={5} style={{ height: "100%", width: "100%" }} scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="/api/v1/tiles/{z}/{x}/{y}.png"
      />
      <FlyToSelected selected={selected} />
      <ClickToAnalyze onClick={handleMapClick} />

      {/* data layers (real: INCOIS PFZ / JTWC / MarineRegions) */}
      {lineFeatures.length > 0 && (
        <GeoJSON
          key={`gj-${lineFeatures.length}-${lineFeatures[0]?.properties?.advisory_date ?? ""}-${JSON.stringify(enabled)}`}
          data={geoJsonData as any}
          style={(f: any) => LAYER_STYLES[f?.properties?.layer] ?? { color: "#555", weight: 1 }}
        />
      )}
      {pointFeatures.map((f: any, i: number) => {
        const [lo, la] = f.geometry.coordinates;
        const p = f.properties ?? {};
        const isCyclone = p.layer === "cyclone";
        // Indian-ocean system → alert red. Far-away basin → muted gray,
        // so a Japan-side typhoon never looks like a local threat.
        const cycloneRelevant = p.indian_region !== false;
        return (
          <CircleMarker
            key={`pt-${i}`}
            center={[la, lo]}
            radius={isCyclone ? 10 : 4}
            pathOptions={
              isCyclone
                ? cycloneRelevant
                  ? { color: "#ea580c", fillColor: "#ea580c", fillOpacity: 0.7, weight: 2 }
                  : { color: "#94a3b8", fillColor: "#cbd5e1", fillOpacity: 0.45, weight: 1.5, dashArray: "4 4" }
                : { color: "#475569", fillColor: "#94a3b8", fillOpacity: 0.9, weight: 1 }
            }
          >
            <Popup>
              {isCyclone ? (
                <div>
                  <strong>🌀 {p.name ?? "Tropical cyclone"}</strong><br />
                  {p.intensity ?? ""} · max wind {p.max_wind_kt ?? "?"} kn<br />
                  moving {p.movement_deg ?? "?"}° at {p.movement_kt ?? "?"} kn<br />
                  {p.advisory_no != null && (
                    <>✅ official JTWC advisory #{p.advisory_no}<br /></>
                  )}
                  {p.basin_name && (
                    <>
                      basin: {p.basin_name}
                      {!cycloneRelevant && " — outside Indian Ocean, shown for awareness only"}
                      <br />
                    </>
                  )}
                  <em>{p.source}</em>
                </div>
              ) : (
                <div>
                  <strong>⚓ {p.name}</strong><br />
                  {p.state ?? ""}
                </div>
              )}
            </Popup>
          </CircleMarker>
        );
      })}

      {/* selected point — pulsing crosshair so the analysed spot is unmistakable */}
      {selected && (
        <>
          <CircleMarker
            center={[selected.lat, selected.lon]}
            radius={9}
            pathOptions={{ color: "#22d3ee", weight: 2.5, fillColor: "#22d3ee", fillOpacity: 0.35 }}
          >
            <Popup>
              <div>
                <strong>📍 {selected.name}</strong><br />
                {selected.lat.toFixed(3)}°N, {selected.lon.toFixed(3)}°E<br />
                <em>{lang === "hi" ? "यहाँ का विश्लेषण दाहिने पैनल में" : "analysis for this point is in the right panel"}</em>
              </div>
            </Popup>
          </CircleMarker>
          <CircleMarker
            center={[selected.lat, selected.lon]}
            radius={20}
            pathOptions={{ color: "#22d3ee", weight: 1, dashArray: "4 4", fillOpacity: 0, opacity: 0.5 }}
          />
        </>
      )}

      {/* zone markers */}
      {zones.map((z) => (
        <Marker key={z.name} position={[z.lat, z.lon]} eventHandlers={{ click: () => onSelect(z) }}>
          <Popup>
            <strong>{z.name}</strong><br />
            {z.lat.toFixed(2)}°N, {z.lon.toFixed(2)}°E<br />
            <button
              onClick={() => onSelect(z)}
              className="mt-1 text-xs bg-blue-600 text-white px-2 py-1 rounded"
            >
              Analyze →
            </button>
          </Popup>
        </Marker>
      ))}

      {/* layer toggles + actions (top-right overlay) */}
      <div className="leaflet-top leaflet-right">
        <div className="leaflet-control bg-[#0E1729]/95 border border-[#1C2A45] text-slate-200 rounded-lg shadow-xl p-2.5 m-2 space-y-1.5 w-[220px] backdrop-blur">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{t(lang, "map_layers")}</div>
          {LAYER_KEYS.map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer hover:text-slate-100">
              <input
                type="checkbox"
                className="accent-cyan-400"
                checked={!!enabled[key]}
                onChange={(e) => setEnabled((s) => ({ ...s, [key]: e.target.checked }))}
              />
              {label}
            </label>
          ))}
          <button
            onClick={loadLayers}
            className="w-full mt-1 text-xs bg-[#131E35] hover:bg-[#16243F] border border-[#2B4066] rounded px-2 py-1"
          >
            ↻ {t(lang, "refresh")}
          </button>
          <button
            onClick={locateMe}
            className="w-full text-xs bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 rounded px-2 py-1"
          >
            {t(lang, "my_location")}
          </button>
          {layersErr && <div className="text-[10px] text-red-400">{layersErr}</div>}
          {layers && (
            <div className="text-[10px] text-slate-500">
              {layers.features.length} features · {layers.sources.join(", ")}
            </div>
          )}
        </div>
      </div>
    </MapContainer>
  );
}
