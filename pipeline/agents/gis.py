"""Deterministic GIS context agent.

Phase 1 has a real GLOBE land/sea mask and a small static ORCA port
reference list. It does *not* have the authoritative PostGIS-backed EEZ,
marine-protected-area, restricted-zone, or navigation-chart datasets requested
by the target architecture. Consequently this agent never turns a bounding box
or a hand-drawn radius into a legal classification.

The map layer service can fetch an India EEZ polygon from MarineRegions on
demand, but that optional display layer is not treated as a safety/legal check.
"""
from __future__ import annotations

import math
from typing import Any

from pipeline import landmask

# Static reference coordinates retained from the integrated implementation.
# Their upstream per-record citations were not supplied, so every result labels
# this provenance limitation instead of calling the list authoritative.
INDIAN_PORTS = [
    {"name": "Mumbai (JNPT)", "lat": 18.95, "lon": 72.95},
    {"name": "Mumbai (Mumbai Port)", "lat": 18.94, "lon": 72.84},
    {"name": "Kandla", "lat": 23.03, "lon": 70.22},
    {"name": "Mundra", "lat": 22.74, "lon": 69.72},
    {"name": "Mangalore (New Mangalore)", "lat": 12.92, "lon": 74.80},
    {"name": "Cochin", "lat": 9.97, "lon": 76.29},
    {"name": "Tuticorin", "lat": 8.76, "lon": 78.20},
    {"name": "Chennai", "lat": 13.10, "lon": 80.30},
    {"name": "Ennore", "lat": 13.26, "lon": 80.32},
    {"name": "Krishnapatnam", "lat": 14.25, "lon": 80.13},
    {"name": "Visakhapatnam", "lat": 17.68, "lon": 83.28},
    {"name": "Paradip", "lat": 20.27, "lon": 86.61},
    {"name": "Haldia", "lat": 22.03, "lon": 88.07},
    {"name": "Kolkata", "lat": 22.55, "lon": 88.31},
    {"name": "Port Blair", "lat": 11.62, "lon": 92.73},
    {"name": "Kavaratti", "lat": 10.57, "lon": 72.64},
]
PORT_SOURCE = "ORCA static port reference list (upstream per-record citations pending)"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    radius_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def _nearest_port(lat: float, lon: float, k: int = 3) -> list[dict[str, Any]]:
    distances = [
        {**port, "distance_km": round(_haversine_km(lat, lon, port["lat"], port["lon"]), 1),
         "source": PORT_SOURCE}
        for port in INDIAN_PORTS
    ]
    return sorted(distances, key=lambda port: port["distance_km"])[:k]


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    lat = snap.get("lat")
    lon = snap.get("lon")
    if lat is None or lon is None:
        return {
            "agent": "gis",
            "findings": [{
                "type": "no_location", "severity": "info", "value": None,
                "msg": "No lat/lon — spatial context cannot be evaluated.",
            }],
            "summary": "No spatial data.",
            "risk_level": "unknown",
            "status": "degraded",
        }

    findings: list[dict[str, Any]] = []
    land = landmask.is_land(float(lat), float(lon))
    findings.append({
        "type": "globe_land_state",
        "severity": "info",
        "value": land,
        "source": "GLOBE 1 km land mask (global-land-mask package)",
        "msg": (
            "GLOBE classifies the requested point as land."
            if land is True else
            "GLOBE classifies the requested point as water."
            if land is False else
            "GLOBE land/water classification is unavailable."
        ),
    })

    ports = _nearest_port(float(lat), float(lon), k=2)
    findings.append({
        "type": "nearest_ports_reference",
        "severity": "info",
        "value": ports,
        "source": PORT_SOURCE,
        "provenance_pending": True,
        "msg": (
            "Static reference only (not a navigation source): "
            + ", ".join(f"{port['name']} ({port['distance_km']} km)" for port in ports)
            + "."
        ),
    })
    findings.append({
        "type": "authoritative_boundaries_unavailable",
        "severity": "info",
        "value": None,
        "msg": (
            "Authoritative EEZ, MPA, restricted-zone and nautical-chart polygons "
            "are not integrated; no legal boundary classification was performed."
        ),
    })

    return {
        "agent": "gis",
        "findings": findings,
        "summary": "🗺️ Land/sea context checked; legal marine boundaries remain unavailable.",
        "risk_level": "unknown",
        "status": "degraded",
    }
