"""GeoJSON map layers — every feature traceable to a real source.

Layers:
  official_pfz   Today's INCOIS PFZ advisory lines (GeoServer WFS, live)
  cyclone        Active JTWC cyclone positions + 34-kt wind radius (live)
  port           Indian fishing harbours (curated gazetteer — ports don't
                 move; coordinates from official port records)
  eez            India mainland EEZ + territorial boundary
                 (MarineRegions, the reference maritime-boundary database)

The restricted-zones layer from the blueprint is intentionally NOT faked:
we only ship boundaries we can cite. The 12 NM territorial line is real
and meaningful (different fishing rules inside it).
"""
from __future__ import annotations

import json
import math
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pipeline import incois_pfz, jtwc
from pipeline.ttlcache import cached

# Indian major fishing harbours / landing centres — real coordinates.
# (State, harbour). Not exhaustive; the 15 largest landing centres.
PORTS: list[dict[str, Any]] = [
    {"name": "Veraval",          "state": "Gujarat",          "lat": 20.90, "lon": 70.37},
    {"name": "Porbandar",        "state": "Gujarat",          "lat": 21.64, "lon": 69.63},
    {"name": "Okha",             "state": "Gujarat",          "lat": 22.46, "lon": 69.07},
    {"name": "Mumbai (Sassoon Dock)", "state": "Maharashtra", "lat": 18.92, "lon": 72.83},
    {"name": "Ratnagiri",        "state": "Maharashtra",      "lat": 16.99, "lon": 73.31},
    {"name": "Malvan",           "state": "Maharashtra",      "lat": 16.06, "lon": 73.47},
    {"name": "Malpe",            "state": "Karnataka",        "lat": 13.35, "lon": 74.70},
    {"name": "Mangalore",        "state": "Karnataka",        "lat": 12.91, "lon": 74.81},
    {"name": "Kochi (Cochin)",   "state": "Kerala",           "lat": 9.94,  "lon": 76.26},
    {"name": "Thiruvananthapuram (Vizhinjam)", "state": "Kerala", "lat": 8.38, "lon": 76.98},
    {"name": "Tuticorin",        "state": "Tamil Nadu",       "lat": 8.76,  "lon": 78.16},
    {"name": "Chennai",          "state": "Tamil Nadu",       "lat": 13.10, "lon": 80.29},
    {"name": "Visakhapatnam",    "state": "Andhra Pradesh",   "lat": 17.68, "lon": 83.30},
    {"name": "Paradip",          "state": "Odisha",           "lat": 20.26, "lon": 86.63},
    {"name": "Digha",            "state": "West Bengal",      "lat": 21.63, "lon": 87.51},
]

ALL_LAYERS = ("official_pfz", "cyclone", "port", "eez")


def _circle_polygon(lat: float, lon: float, radius_km: float, n: int = 48) -> list[list[float]]:
    """Approximate a circle on the sphere as a polygon ring (GeoJSON coords)."""
    ring = []
    R = 6371.0088
    d = radius_km / R
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    for i in range(n + 1):
        brng = 2 * math.pi * i / n
        la2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brng))
        lo2 = lon1 + math.atan2(
            math.sin(brng) * math.sin(d) * math.cos(lat1),
            math.cos(d) - math.sin(lat1) * math.sin(la2),
        )
        ring.append([round(math.degrees(lo2), 4), round(math.degrees(la2), 4)])
    return ring


# ── EEZ boundary (MarineRegions WFS) ───────────────────────────────

_EEZ_WFS = (
    "https://geo.vliz.be/geoserver/MarineRegions/ows"
    "?service=WFS&version=1.0.0&request=GetFeature"
    "&typeName=MarineRegions%3Aeez&outputFormat=application%2Fjson"
    "&CQL_FILTER=mrgid%3D8480"  # India mainland EEZ (mrgid 8480)
)


def _fetch_eez() -> dict[str, Any] | None:
    req = urllib.request.Request(_EEZ_WFS, headers={"User-Agent": "ORCA/1.0 (SIH 2026)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.loads(r.read().decode("utf-8"))
    feats = raw.get("features", [])
    if not feats:
        return None
    return feats[0]


def _eez_feature() -> dict[str, Any] | None:
    try:
        feat = cached("eez_india", 24 * 3600, _fetch_eez)
        if not feat:
            return None
        return {
            "type": "Feature",
            "geometry": feat["geometry"],
            "properties": {
                "layer": "eez",
                "name": "India Exclusive Economic Zone (200 NM limit)",
                "source": "MarineRegions (Flanders Marine Institute)",
            },
        }
    except Exception:  # noqa: BLE001
        return None  # boundary is nice-to-have; never break the map for it


# ── Layer assembly ─────────────────────────────────────────────────

def get_layers(
    bbox: tuple[float, float, float, float] | None = None,
    types: list[str] | None = None,
) -> dict[str, Any]:
    """FeatureCollection of the requested layers.
    bbox = (min_lon, min_lat, max_lon, max_lat)."""
    wanted = set(types or ALL_LAYERS)
    features: list[dict[str, Any]] = []
    errors: list[str] = []
    sources: set[str] = set()

    if "official_pfz" in wanted:
        pfz_feats = incois_pfz.as_geojson_features(bbox)
        if pfz_feats:
            features += pfz_feats
            sources.add(incois_pfz.SOURCE_LABEL)
        else:
            try:
                data = incois_pfz.get_lines()
                if not data["lines"]:
                    errors.append("INCOIS PFZ: today's advisory has no lines (cloud cover or no advisory yet)")
            except Exception as e:  # noqa: BLE001
                errors.append(f"INCOIS PFZ: {type(e).__name__}")

    if "cyclone" in wanted:
        try:
            data = jtwc.get_active_cyclones()
            sources.add(jtwc.SOURCE_LABEL)
            for c in data["cyclones"]:
                label = c.get("name") or c["designation"]
                basin = c.get("basin")  # wp | io | sh
                # ORCA serves Indian waters: Indian-ocean basins are
                # "relevant" and drawn in alert red; far-away systems
                # (e.g. a Japan-side typhoon) stay visible but muted so
                # the map never cries wolf. (Screenshot review 2026-09-04:
                # out-of-basin cyclones looked identical to local threats.)
                relevant = basin in ("io", "sh")
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                    "properties": {
                        "layer": "cyclone",
                        "name": label,
                        "intensity": c.get("intensity"),
                        "max_wind_kt": c.get("max_wind_kt"),
                        "movement_deg": c.get("movement_deg"),
                        "movement_kt": c.get("movement_kt"),
                        "advisory_no": c.get("advisory_no"),
                        "basin": basin,
                        "basin_name": c.get("basin_name"),
                        "indian_region": relevant,
                        "source": jtwc.SOURCE_LABEL,
                    },
                })
                if c.get("radius_34kt_nm"):
                    r_km = c["radius_34kt_nm"] * 1.852
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [_circle_polygon(c["lat"], c["lon"], r_km)],
                        },
                        "properties": {
                            "layer": "cyclone_radius",
                            "name": f"{label} — 34 kt (gale) wind radius",
                            "radius_nm": c["radius_34kt_nm"],
                            "source": jtwc.SOURCE_LABEL,
                        },
                    })
            if data.get("errors") and not data["cyclones"]:
                errors.append(f"JTWC: {data['errors'][0]}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"JTWC: {type(e).__name__}")

    if "port" in wanted:
        for p in PORTS:
            if bbox and not (bbox[0] <= p["lon"] <= bbox[2] and bbox[1] <= p["lat"] <= bbox[3]):
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                "properties": {"layer": "port", "name": p["name"], "state": p["state"]},
            })

    if "eez" in wanted:
        feat = _eez_feature()
        if feat:
            features.append(feat)
            sources.add("MarineRegions (Flanders Marine Institute)")

    return {
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": features,
        "layer_types": sorted(wanted),
        "sources": sorted(sources),
        "errors": errors,
    }
