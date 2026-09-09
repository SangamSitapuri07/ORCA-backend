"""INCOIS official Potential Fishing Zone (PFZ) advisory lines — the REAL thing.

INCOIS (Indian National Centre for Ocean Information Services) publishes a
daily PFZ advisory from Oceansat/OCM + SST analysis. Fishers know it as the
official "kahaan machli milegi" bulletin. It used to be published only as a
PDF/map image per sector, but their automation pipeline exposes the raw
advisory lines through a public GeoServer WFS:

    https://incois.gov.in/geoserver/PFZ_Automation/ows
      ?service=WFS&version=1.0.0&request=GetFeature
      &typeName=PFZ_Automation:pfzlines&outputFormat=application/json

Each feature is a MultiLineString with properties:
    SECTORBOUN  sector numeric code (3 = Maharashtra, 5 = Karnataka, ...)
    Julian_day  day-of-year the advisory is for ("246" = 3 Sep 2026)
    Year        2026
    UID         Year*1000 + Julian_day*100 + serial  (e.g. 2026246001)
    Length      line length (km)

Verified live on 2026-09-03: 80 advisory lines for Julian day 246 (today).

We use this for three things:
  1. "Nearest official PFZ" distance/bearing in the advisory card
  2. PFZ layer on the map (green dashed lines — the official advisory)
  3. Ground truth for validating our own PFZ prototype
"""
from __future__ import annotations

import json
import math
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pipeline.ttlcache import cached

WFS_URL = (
    "https://incois.gov.in/geoserver/PFZ_Automation/ows"
    "?service=WFS&version=1.0.0&request=GetFeature"
    "&typeName=PFZ_Automation%3Apfzlines&outputFormat=application/json"
)
SOURCE_LABEL = "INCOIS PFZ Advisory (GeoServer WFS)"
USER_AGENT = "ORCA/1.0 (SIH 2026; marine research)"

# Sector codes as published in INCOIS PFZ advisories. Sectors we haven't
# confirmed yet are labelled generically instead of being invented.
SECTOR_NAMES: dict[int, str] = {
    1: "Lakshadweep",
    3: "Maharashtra",
    4: "Kerala",
    5: "Karnataka",
    6: "Goa",
    8: "Tamil Nadu",
    9: "Andhra Pradesh",
    10: "North Andhra / Odisha",
}

TTL_SEC = 6 * 3600  # advisory is daily; 6 h is a safe cache window


# ── Geodesy helpers (stdlib only) ──────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing from point 1 to point 2 (0-360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _point_segment_km(
    lat: float, lon: float, lat_a: float, lon_a: float, lat_b: float, lon_b: float
) -> tuple[float, tuple[float, float]]:
    """Distance (km) from point to great-circle segment.

    Approximated on a local equirectangular plane centred at the point —
    well within 0.5% for segments under ~500 km (PFZ lines are 10-200 km).
    Returns (distance_km, (closest_lat, closest_lon)).
    """
    lat0 = math.radians(lat)

    def to_xy(la: float, lo: float) -> tuple[float, float]:
        return (
            math.radians(lo - lon) * math.cos(lat0) * 6371.0088,
            math.radians(la - lat) * 6371.0088,
        )

    xa, ya = to_xy(lat_a, lon_a)
    xb, yb = to_xy(lat_b, lon_b)
    dx, dy = xb - xa, yb - ya
    if dx == 0 and dy == 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, -(xa * dx + ya * dy) / (dx * dx + dy * dy)))
    cx, cy = xa + t * dx, ya + t * dy
    dist = math.hypot(cx, cy)
    # convert closest point back to lat/lon
    clat = lat + math.degrees(cy / 6371.0088)
    clon = lon + math.degrees(cx / (6371.0088 * math.cos(lat0)))
    return dist, (clat, clon)


def distance_to_polyline_km(
    lat: float, lon: float, coords: list[list[float]]
) -> tuple[float, tuple[float, float]]:
    """Min distance from point to a polyline ([[lon, lat], ...])."""
    best = math.inf
    best_pt = (coords[0][1], coords[0][0])
    for i in range(len(coords) - 1):
        lo_a, la_a = coords[i][0], coords[i][1]
        lo_b, la_b = coords[i + 1][0], coords[i + 1][1]
        d, pt = _point_segment_km(lat, lon, la_a, lo_a, la_b, lo_b)
        if d < best:
            best, best_pt = d, pt
    return best, best_pt


# ── Fetch & normalize ───────────────────────────────────────────────

def _fetch_now() -> dict[str, Any]:
    req = urllib.request.Request(WFS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=12) as r:
        raw = json.loads(r.read().decode("utf-8"))

    lines: list[dict[str, Any]] = []
    for feat in raw.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        # Flatten MultiLineString / LineString into separate lines
        polylines: list[list[list[float]]] = []
        if gtype == "MultiLineString":
            polylines = [c for c in coords if c]
        elif gtype == "LineString" and coords:
            polylines = [coords]
        sector = props.get("SECTORBOUN")
        for i, pl in enumerate(polylines):
            if len(pl) < 2:
                continue
            lines.append({
                "uid": props.get("UID"),
                "sno": props.get("Sno"),
                "sector_code": sector,
                "sector_name": SECTOR_NAMES.get(int(sector), f"Sector {sector}")
                if sector is not None else None,
                "julian_day": props.get("Julian_day"),
                "year": props.get("Year"),
                "length_km": round(props.get("Length", 0.0), 1),
                "part": i,
                "coords": pl,  # [[lon, lat], ...]
            })

    julian_days = [l["julian_day"] for l in lines if l["julian_day"]]
    latest_jd = max(julian_days) if julian_days else None
    year = lines[0]["year"] if lines else None
    advisory_date = None
    if latest_jd and year:
        try:
            d0 = datetime(int(year), 1, 1, tzinfo=timezone.utc)
            from datetime import timedelta
            advisory_date = (d0 + timedelta(days=int(latest_jd) - 1)).date().isoformat()
        except (ValueError, TypeError):
            advisory_date = None

    return {
        "source": SOURCE_LABEL,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_lines": len(lines),
        "latest_julian_day": latest_jd,
        "year": year,
        "advisory_date": advisory_date,
        "lines": lines,
    }


def get_lines(force: bool = False, latest_only: bool = True) -> dict[str, Any]:
    """Cached PFZ advisory lines. `latest_only` filters to the newest
    Julian day (the current advisory) — older lines in the file are stale."""
    if force:
        from pipeline import ttlcache
        with ttlcache._lock:
            ttlcache._store.pop("incois_pfz", None)
    data = cached("incois_pfz", TTL_SEC, _fetch_now)
    if latest_only and data.get("latest_julian_day"):
        jd = data["latest_julian_day"]
        return {**data, "lines": [l for l in data["lines"] if l["julian_day"] == jd]}
    return data


# ── Queries ─────────────────────────────────────────────────────────

def nearest_pfz(lat: float, lon: float) -> dict[str, Any]:
    """Distance + bearing to the nearest official INCOIS PFZ line,
    or an honest `None` result if today's advisory has no lines near
    the point's sector (e.g. monsoon cloud cover — no advisories that day)."""
    try:
        data = get_lines()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}

    lines = [l for l in data["lines"]]
    # Quick pre-filter: ignore lines whose bbox is > 3° away
    near = [
        l for l in lines
        if min(c[1] for c in l["coords"]) - 3 <= lat <= max(c[1] for c in l["coords"]) + 3
        and min(c[0] for c in l["coords"]) - 3 <= lon <= max(c[0] for c in l["coords"]) + 3
    ]
    if not near:
        return {
            "available": bool(lines),
            "found": False,
            "advisory_date": data.get("advisory_date"),
            "note": "No official PFZ line within ~300 km of this point today.",
        }

    best = math.inf
    best_line: dict[str, Any] | None = None
    best_pt: tuple[float, float] | None = None
    for l in near:
        d, pt = distance_to_polyline_km(lat, lon, l["coords"])
        if d < best:
            best, best_line, best_pt = d, l, pt

    assert best_line is not None and best_pt is not None
    return {
        "available": True,
        "found": True,
        "distance_km": round(best, 1),
        "distance_nm": round(best / 1.852, 1),
        "bearing_deg": round(bearing_deg(lat, lon, best_pt[0], best_pt[1])),
        "nearest_point": {"lat": round(best_pt[0], 4), "lon": round(best_pt[1], 4)},
        "sector_name": best_line["sector_name"],
        "uid": best_line["uid"],
        "line_length_km": best_line["length_km"],
        "advisory_date": data.get("advisory_date"),
        "julian_day": data.get("latest_julian_day"),
        "source": SOURCE_LABEL,
    }


def as_geojson_features(bbox: tuple[float, float, float, float] | None = None) -> list[dict[str, Any]]:
    """GeoJSON LineString features for the map layer.
    bbox = (min_lon, min_lat, max_lon, max_lat) optional filter."""
    try:
        data = get_lines()
    except Exception:  # noqa: BLE001
        return []
    feats = []
    for l in data["lines"]:
        if bbox:
            xs = [c[0] for c in l["coords"]]
            ys = [c[1] for c in l["coords"]]
            if not (min(xs) <= bbox[2] and max(xs) >= bbox[0]
                    and min(ys) <= bbox[3] and max(ys) >= bbox[1]):
                continue
        feats.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": l["coords"]},
            "properties": {
                "layer": "official_pfz",
                "sector_name": l["sector_name"],
                "uid": l["uid"],
                "length_km": l["length_km"],
                "advisory_date": data.get("advisory_date"),
                "source": SOURCE_LABEL,
            },
        })
    return feats
