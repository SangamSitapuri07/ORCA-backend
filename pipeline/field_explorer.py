"""Field Explorer — a real, sampled VIEW of the ocean around one point.

The map pins in the demo UI are just entry points; the honest question
behind them is "what does the ocean look like AROUND the click?". This
module answers with a sampled grid (~10x10) of REAL values:

  - chlorophyll  : NOAA ERDDAP VIIRS DINEOF, one strided grid query
                   (the same dataset the single-point chlorophyll uses)
  - waves/wind   : Open-Meteo Marine + Forecast, multi-point request
                   (the same models the advisory verdict uses)

Both calls are cached 30 min per rounded centre. The hotspot ranking is
transparent: "fish-attracting productivity" = chlorophyll percentile of
the sampled grid — productively labelled as a proxy, never a fish census.

Land guard: NOAA's DINEOF grid sometimes reports chl ON LAND (coastal
bleed/sediment pixels, inland lakes/lagoons). Those pixels are real
numbers but NOT fishing spots, so every chl cell is checked against the
GLOBE 1 km land mask (pipeline/landmask.py) before it can rank or draw.
"""
from __future__ import annotations

import csv
import io
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pipeline import landmask
from pipeline.erddap_chl import ERDDAP_BASE, _fetch_csv
from pipeline.ttlcache import cached

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "ORCA/1.0 (SIH 2026; marine research)"

# Grid footprint (degrees around the clicked point) and resolution.
RADIUS_DEG = 1.2          # ±1.2° → the fishing-relevant waters around a point
CHL_STEP_DEG = 0.075      # NOAA DINEOF 9 km native step
GRID_TARGET_N = 9         # ~GRID_TARGET_N x GRID_TARGET_N points per variable


def _http_json(url: str, params: dict[str, str], timeout: float = 15.0):
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _compass(deg: float) -> str:
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) // 22.5) % 16]


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# ── coastal-bloom honesty probe ───────────────────────────────────────
# The map legend says ">5 mg/m3 = bloom". Near river mouths (Hooghly,
# Subarnarekha, Narmada...) SUSPENDED SEDIMENT can fool band-ratio
# chlorophyll into bloom-range readings — a live reviewer flagged our
# 11.76 mg/m3 Hooghly hotspot exactly for this. We never hide the value
# (it IS what NOAA measured), but a bloom-range cell sitting within a
# short sail of the coast earns an explicit turbidity caveat.
BLOOM_MG = 5.0            # matches the chl legend's bloom threshold
COASTAL_CAVEAT_KM = 30.0  # "coastal" = land within this sail distance


def _distance_to_land_km(lat: float, lon: float,
                         max_km: float = 60.0, step_km: float = 2.0) -> float | None:
    """Nearest-land probe along 8 compass rays (real GLOBE 1 km mask —
    pure local math, no network, no hardcoded coastline). Returns None
    when the mask is unavailable or no land lies within max_km."""
    if not landmask.enabled():
        return None
    if landmask.is_land(lat, lon) is True:
        return 0.0
    best: float | None = None
    cos_lat = max(0.087, math.cos(math.radians(lat)))
    for brg in range(0, 360, 45):
        th = math.radians(brg)
        d = step_km
        while d <= max_km:
            plat = lat + d * math.cos(th) / 111.32
            plon = lon + d * math.sin(th) / (111.32 * cos_lat)
            if landmask.is_land(plat, plon) is True:
                best = d if best is None else min(best, d)
                break
            d += step_km
    return best


# ── chlorophyll grid (one ERDDAP call) ───────────────────────────────

def fetch_chl_grid(lat: float, lon: float) -> dict[str, Any]:
    """Strided ERDDAP grid query around (lat, lon). One HTTP call.

    Uses [last] = the latest day ERDDAP has — the same value the
    single-point chlorophyll reads. Rows with NaN are dropped.
    """
    lat_lo, lat_hi = lat - RADIUS_DEG, lat + RADIUS_DEG
    lon_lo, lon_hi = lon - RADIUS_DEG, lon + RADIUS_DEG
    n_native = max(1, round((2 * RADIUS_DEG) / CHL_STEP_DEG))
    stride = max(1, round(n_native / GRID_TARGET_N))

    query = (
        f"chlor_a[last]"
        f"[(0.0):1:(0.0)]"
        f"[({lat_lo:.4f}):{stride}:({lat_hi:.4f})]"
        f"[({lon_lo:.4f}):{stride}:({lon_hi:.4f})]"
    )
    url = f"{ERDDAP_BASE}.csv?{query}"
    print(f"[Field] NOAA chl grid: ({lat:.2f},{lon:.2f}) stride {stride}", file=sys.stderr)
    rows = _fetch_csv(url)

    points: list[dict[str, Any]] = []
    date_seen: str | None = None
    land_masked = 0
    for row in rows:
        raw = row.get("chlor_a")
        if raw in (None, "", "NaN", "nan"):
            continue
        try:
            v = float(raw)
        except ValueError:
            continue
        if v <= 0:
            continue
        plat = round(float(row["latitude"]), 4)
        plon = round(float(row["longitude"]), 4)
        # On-land DINEOF pixels (coastal bleed, lakes/lagoons) are real
        # numbers but never fishing spots — drop them (GLOBE 1 km mask).
        # None (mask unavailable) = no information = KEEP the pixel.
        if landmask.is_land(plat, plon) is True:
            land_masked += 1
            continue
        points.append({
            "lat": plat,
            "lon": plon,
            "chl": round(v, 3),
        })
        if date_seen is None and row.get("time"):
            date_seen = row["time"][:10]

    if land_masked:
        print(f"[Field] land-mask: {land_masked} on-land chl pixels dropped "
              f"(GLOBE 1 km — coastal bleed/lagoon, not fishing spots)", file=sys.stderr)

    return {
        "points": points,
        "date": date_seen or "unknown",
        "n": len(points),
        "land_masked": land_masked,
        "land_mask": "GLOBE 1 km (real)" if landmask.enabled() else "unavailable",
        "source": "NOAA ERDDAP VIIRS DINEOF (9 km, gap-filled)",
    }


# ── weather / waves grid (one multi-point call per API) ─────────────

def _grid_points(lat: float, lon: float) -> list[tuple[float, float]]:
    n = GRID_TARGET_N
    step = (2 * RADIUS_DEG) / (n - 1)
    pts = []
    for i in range(n):
        for j in range(n):
            pts.append((
                round(lat - RADIUS_DEG + i * step, 4),
                round(lon - RADIUS_DEG + j * step, 4),
            ))
    return pts


def fetch_met_grid(lat: float, lon: float) -> dict[str, Any]:
    """Waves + wind for every grid point. Open-Meteo accepts
    comma-separated coordinate lists — ONE call each for marine
    and weather, not one per point."""
    pts = _grid_points(lat, lon)
    lats = ",".join(f"{p[0]:.4f}" for p in pts)
    lons = ",".join(f"{p[1]:.4f}" for p in pts)

    def _as_list(data):
        return data if isinstance(data, list) else [data]

    marine = _as_list(_http_json(MARINE_URL, {
        "latitude": lats,
        "longitude": lons,
        "current": ("wave_height,swell_wave_height,ocean_current_velocity,"
                    "ocean_current_direction,sea_surface_temperature"),
        "timezone": "UTC",
    }))
    weather = _as_list(_http_json(FORECAST_URL, {
        "latitude": lats,
        "longitude": lons,
        "current": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
        "wind_speed_unit": "kn",
        "timezone": "UTC",
    }))
    print(f"[Field] met grid: {len(marine)} marine + {len(weather)} wx cells", file=sys.stderr)

    points: list[dict[str, Any]] = []
    for p, m, w in zip(pts, marine, weather):
        mc = (m or {}).get("current") or {}
        wc = (w or {}).get("current") or {}
        ocv = mc.get("ocean_current_velocity")
        points.append({
            "lat": p[0],
            "lon": p[1],
            # real GLOBE 1 km land check — True/False/None(unknown), so the
            # UI can honestly mark on-land cells (values are the nearest
            # sea cell's, which IS useful right at the coast)
            "land": landmask.is_land(p[0], p[1]),
            "wave_m": mc.get("wave_height"),
            "swell_m": mc.get("swell_wave_height"),
            "current_kn": round(ocv * 1.943844, 2) if isinstance(ocv, (int, float)) else None,
            "current_dir_deg": mc.get("ocean_current_direction"),
            "sst_c": mc.get("sea_surface_temperature"),
            "wind_kn": wc.get("wind_speed_10m"),
            "gust_kn": wc.get("wind_gusts_10m"),
            "wind_dir_deg": wc.get("wind_direction_10m"),
        })
    return {
        "points": points,
        "n": len(points),
        "source": "Open-Meteo Marine + Forecast (MeteoFrance/ECMWF)",
    }


# ── hotspot ranking ──────────────────────────────────────────────────

def _hotspots(chl_points: list[dict[str, Any]], lat: float, lon: float,
              top: int = 3) -> list[dict[str, Any]]:
    """Highest-chlorophyll cells = fish-attracting productivity hotspots.

    Labelled honestly: this is a plankton→baitfish→fish chain proxy,
    NOT an AIS/fishery catch count (that is GFW's role, shown separately).

    Sea-only: even if an on-land pixel slips past fetch_chl_grid's mask
    (e.g. a hand-built list), it can never rank as a "fishing hotspot".
    """
    sea = [p for p in chl_points if landmask.is_land(p["lat"], p["lon"]) is not True]
    ranked = sorted(sea, key=lambda p: -p["chl"])[:top]
    out = []
    for p in ranked:
        d = _haversine_km(lat, lon, p["lat"], p["lon"])
        coast_km = _distance_to_land_km(p["lat"], p["lon"])
        is_bloom = p["chl"] >= BLOOM_MG
        caveat = None
        if is_bloom and coast_km is not None and coast_km <= COASTAL_CAVEAT_KM:
            caveat = (
                "coastal bloom: river-mouth turbidity (suspended sediment) can "
                "inflate satellite chl here — cross-check INCOIS PFZ before steaming far"
            )
        out.append({
            "lat": p["lat"],
            "lon": p["lon"],
            "chl": p["chl"],
            "distance_km": round(d, 1),
            "distance_nm": round(d / 1.852, 1),
            "bearing": _compass(_bearing(lat, lon, p["lat"], p["lon"])),
            "bloom": is_bloom,
            "coast_km": coast_km,
            "caveat": caveat,
        })
    return out


# ── public entry ─────────────────────────────────────────────────────

def get_field(lat: float, lon: float) -> dict[str, Any]:
    """One cached call (30 min per 0.1° centre) powering the explorer."""
    key = f"field:{lat:.1f}:{lon:.1f}"
    return cached(key, 1800, lambda: _build(lat, lon))


def _build(lat: float, lon: float) -> dict[str, Any]:
    chl: dict[str, Any] = {"points": [], "error": None}
    met: dict[str, Any] = {"points": [], "error": None}
    try:
        chl = fetch_chl_grid(lat, lon)
    except Exception as e:  # noqa: BLE001
        chl = {"points": [], "error": f"{type(e).__name__}: {e}", "n": 0}
    try:
        met = fetch_met_grid(lat, lon)
    except Exception as e:  # noqa: BLE001
        met = {"points": [], "error": f"{type(e).__name__}: {e}", "n": 0}

    return {
        "type": "field",
        "center": {"lat": lat, "lon": lon},
        "radius_deg": RADIUS_DEG,
        "chl": chl,
        "met": met,
        "hotspots": _hotspots(chl.get("points", []), lat, lon) if chl.get("points") else [],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "Chlorophyll hotspots mark plankton-rich water that attracts "
            "baitfish (productivity proxy — not a direct fish count). "
            "On-land pixels (coastal bleed, lakes/lagoons like Chilika) "
            "are excluded with the real GLOBE 1 km land mask, so a "
            "hotspot can never sit on dry ground. "
            "Waves/wind are sampled at the same grid cells."
        ),
    }
