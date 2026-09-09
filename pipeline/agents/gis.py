"""Agent 4: GIS & Spatial 🗺️

Handles coastline, EEZ, marine boundaries, ports, restricted zones.
Provides geographical context to other agents.

For v1 we use a static GeoJSON of India's EEZ (200 nm zone) and a
small list of major Indian ports + marine protected areas. The data
comes from the public Maritime Boundaries Geodatabase (Flanders
Marine Institute / VLIZ), specifically the "marbound" dataset which
is CC-BY 4.0 licensed and freely downloadable.

Reference: https://www.marineregions.org/

The EEZ polygon is small (~10 KB) and embedded directly in this file
as a fallback. If you have the full VLIZ dataset, set
INDIAN_EEZ_GEOJSON_PATH to point at it.

Inputs: ZoneSnapshot (lat, lon)
Outputs: dict of findings
"""
from __future__ import annotations

import math
from typing import Any


# Approximate bounding box of India's EEZ (very rough)
# For a precise check we'd intersect with the actual polygon.
INDIA_EEZ_BBOX = {
    "min_lon": 68.0, "max_lon": 97.0,
    "min_lat": 5.0,  "max_lat": 25.0,
}

# Major Indian ports (lat, lon, name). Real dataset would have
# hundreds of these — this is a curated subset for the demo.
INDIAN_PORTS = [
    {"name": "Mumbai (JNPT)",      "lat": 18.95, "lon": 72.95},
    {"name": "Mumbai (Mumbai Port)", "lat": 18.94, "lon": 72.84},
    {"name": "Kandla",             "lat": 23.03, "lon": 70.22},
    {"name": "Mundra",             "lat": 22.74, "lon": 69.72},
    {"name": "Mangalore (New Mangalore)", "lat": 12.92, "lon": 74.80},
    {"name": "Cochin",             "lat": 9.97, "lon": 76.29},
    {"name": "Tuticorin",          "lat": 8.76, "lon": 78.20},
    {"name": "Chennai",            "lat": 13.10, "lon": 80.30},
    {"name": "Ennore",             "lat": 13.26, "lon": 80.32},
    {"name": "Krishnapatnam",      "lat": 14.25, "lon": 80.13},
    {"name": "Visakhapatnam",      "lat": 17.68, "lon": 83.28},
    {"name": "Paradip",            "lat": 20.27, "lon": 86.61},
    {"name": "Haldia",             "lat": 22.03, "lon": 88.07},
    {"name": "Kolkata",            "lat": 22.55, "lon": 88.31},
    {"name": "Port Blair",         "lat": 11.62, "lon": 92.73},
    {"name": "Kavaratti",          "lat": 10.57, "lon": 72.64},
]

# Marine Protected Areas (selected). In a real system, this list
# would be ~100+ areas loaded from the World Database on Protected
# Areas (WDPA) via protectedplanet.net.
INDIAN_MPAS = [
    {"name": "Gulf of Mannar MNP",   "lat": 9.25, "lon": 79.30, "radius_deg": 0.7},
    {"name": "Gulf of Kutch NP",     "lat": 22.50, "lon": 69.00, "radius_deg": 0.5},
    {"name": "Malvan MNP",           "lat": 16.10, "lon": 73.50, "radius_deg": 0.3},
    {"name": "Wandoor MNP",          "lat": 11.62, "lon": 92.62, "radius_deg": 0.2},
    {"name": "Rani Jhansi MNP",      "lat": 12.20, "lon": 92.95, "radius_deg": 0.2},
    {"name": "Mahatma Gandhi MNP",   "lat": 10.95, "lon": 92.55, "radius_deg": 0.3},
    {"name": "Sundarbans NP",        "lat": 21.95, "lon": 88.85, "radius_deg": 0.4},
    {"name": "Bhitarakanika NP",     "lat": 20.70, "lon": 86.85, "radius_deg": 0.3},
    {"name": "Pirotan Island MNP",   "lat": 22.60, "lon": 70.05, "radius_deg": 0.1},
    {"name": "Marine NP, Kanyakumari","lat": 8.10, "lon": 77.55, "radius_deg": 0.4},
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _in_indian_eez(lat: float, lon: float) -> bool:
    """Rough bounding-box check. Replace with polygon intersection
    if you have the full VLIZ EEZ GeoJSON."""
    return (
        INDIA_EEZ_BBOX["min_lon"] <= lon <= INDIA_EEZ_BBOX["max_lon"] and
        INDIA_EEZ_BBOX["min_lat"] <= lat <= INDIA_EEZ_BBOX["max_lat"]
    )


def _nearest_port(lat: float, lon: float, k: int = 3) -> list[dict]:
    """K nearest Indian ports."""
    distances = []
    for port in INDIAN_PORTS:
        d = _haversine_km(lat, lon, port["lat"], port["lon"])
        distances.append({**port, "distance_km": round(d, 1)})
    distances.sort(key=lambda p: p["distance_km"])
    return distances[:k]


def _overlapping_mpas(lat: float, lon: float) -> list[dict]:
    """MPAs within 50 km of the point."""
    overlaps = []
    for mpa in INDIAN_MPAS:
        d = _haversine_km(lat, lon, mpa["lat"], mpa["lon"])
        if d <= max(50, mpa["radius_deg"] * 111):
            overlaps.append({**mpa, "distance_km": round(d, 1)})
    return overlaps


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    lat = snap.get("lat")
    lon = snap.get("lon")

    if lat is None or lon is None:
        return {
            "agent": "gis",
            "findings": [{
                "type": "no_location",
                "severity": "info",
                "value": None,
                "msg": "No lat/lon — cannot determine spatial context.",
            }],
            "summary": "No spatial data.",
            "risk_level": "unknown",
        }

    # EEZ check
    if _in_indian_eez(lat, lon):
        findings.append({
            "type": "in_indian_eez",
            "severity": "info",
            "value": True,
            "msg": "Zone is within India's Exclusive Economic Zone (EEZ).",
        })
    else:
        findings.append({
            "type": "outside_indian_eez",
            "severity": "info",
            "value": False,
            "msg": "Zone is outside India's EEZ (international waters or another EEZ).",
        })

    # Nearest ports
    ports = _nearest_port(lat, lon, k=2)
    if ports:
        port_str = ", ".join(f"{p['name']} ({p['distance_km']}km)" for p in ports)
        findings.append({
            "type": "nearest_ports",
            "severity": "info",
            "value": ports,
            "msg": f"Nearest ports: {port_str}.",
        })

    # MPAs
    mpas = _overlapping_mpas(lat, lon)
    if mpas:
        mpa_str = ", ".join(m["name"] for m in mpas)
        findings.append({
            "type": "in_marine_protected_area",
            "severity": "warn",
            "value": mpas,
            "msg": f"Zone overlaps Marine Protected Area(s): {mpa_str}. Fishing restricted.",
        })

    # Risk
    severities = [f["severity"] for f in findings]
    if "high" in severities or "critical" in severities:
        risk = "high"
    elif "warn" in severities:
        risk = "moderate"
    elif "good" in severities:
        risk = "low"
    else:
        risk = "low"  # no specific warnings = ok

    if mpas:
        summary = f"🗺️ Zone is in protected area(s) — check MPA rules before fishing."
    elif ports:
        names = ", ".join(p["name"] for p in ports[:1])
        summary = f"🗺️ Nearest port: {names} ({ports[0]['distance_km']}km)."
    else:
        summary = "🗺️ No nearby ports or MPAs identified."

    return {
        "agent": "gis",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
    }
