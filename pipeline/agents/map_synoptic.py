"""Map Synoptic Agent — summarizes real GIS overlays around a zone.

This is a thin adapter over the existing layer service. It uses the bundled,
cited harbour gazetteer only, so it remains deterministic and offline-safe;
live PFZ/cyclone geometries continue to be served by ``/api/v1/layers``.
"""
from __future__ import annotations

from typing import Any

from pipeline import layers


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    lat = snap.get("lat")
    lon = snap.get("lon")
    if lat is None or lon is None:
        return {
            "agent": "map_synoptic",
            "findings": [{
                "type": "no_location",
                "severity": "info",
                "value": None,
                "msg": "No coordinates were supplied; map context was not generated.",
            }],
            "summary": "Map context unavailable without coordinates.",
            "risk_level": "unknown",
        }

    bbox = (float(lon) - 2.0, float(lat) - 2.0, float(lon) + 2.0, float(lat) + 2.0)
    collection = layers.get_layers(bbox=bbox, types=["port"])
    ports = [
        feature for feature in collection.get("features", [])
        if feature.get("properties", {}).get("layer") == "port"
    ]
    names = [str(feature.get("properties", {}).get("name")) for feature in ports[:5]]
    finding = {
        "type": "local_harbour_context",
        "severity": "info",
        "value": len(ports),
        "msg": (
            f"Mapped {len(ports)} cited fishing harbour(s) within the 4° local view"
            + (f": {', '.join(names)}." if names else ".")
        ),
    }
    return {
        "agent": "map_synoptic",
        "findings": [finding],
        "summary": "Deterministic GIS overlay context prepared from the ORCA layer service.",
        "risk_level": "low",
    }
