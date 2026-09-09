"""Open-Meteo Marine API adapter — sea surface temperature, waves, currents.

Open-Meteo (https://open-meteo.com) provides free, no-key, no-registration
access to global marine weather forecast + historical data powered by
MeteoFrance and ECMWF numerical models. This is gold for ORCA because:

- FREE: no API key, no registration, no token
- GLOBAL: covers the full Indian Ocean
- 0.08° resolution (~8 km): fine enough for coastal/regional fish zones
- Daily forecast + historical archive back to 1940
- SST (sea surface temperature), wave height, currents all in one call

Why this matters for ORCA:
- Tuna and pelagic fish aggregate at SST fronts (boundaries between
  warm and cool water). Open-Meteo gives us 0.08° SST daily = the
  front boundaries at 8 km resolution, daily.
- Wave height > 2.5m = unsafe for small fishing vessels. Wave
  advisories for fishermen in their language.
- This is a 2nd independent data source beyond NOAA/MODIS chlorophyll,
  so cross-validation is possible.

The Marine API uses the MeteoFrance wave/SST/currents models:
  https://open-meteo.com/en/docs/marine-weather-api
The Historical Weather API (for past data) uses ERA5:
  https://open-meteo.com/en/docs/historical-weather-api

Usage:
    from pipeline.openmeteo_sst import get_sst_grid, get_sst_at_point
    grid = get_sst_grid(18.0, 20.0, 72.0, 74.0, "2026-08-01", "2026-08-30")
    # Returns: {"points": [{"lat":18.0,"lon":72.0,"sst_max":28.5,"sst_min":28.3,"wave_max":2.86}, ...], ...}
    pt = get_sst_at_point(19.0, 72.8, "2026-08-01", "2026-08-30")
    # Returns: {"sst_mean": 29.0, "sst_max": 29.6, "sst_min": 28.3, "wave_max": 2.86, ...}

Reference: https://marine-api.open-meteo.com/v1/marine
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any


MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"

# MeteoFrance Sea Surface Temperature: 0.08°, 6-hourly, Jan 2022+,
# updated daily. Source: Copernicus GLOBAL_ANALYSISFORECAST_PHY_001_024.
# Variables available as daily aggregates:
#   - sea_surface_temperature_max (°C)
#   - sea_surface_temperature_min (°C)
# As hourly:
#   - sea_surface_temperature (°C)
# Plus wave variables (MeteoFrance MFWAM):
#   - wave_height_max (m, daily)
#   - wave_height (m, hourly)
#   - wave_direction, wave_period
DAILY_VARS = "sea_surface_temperature_max,sea_surface_temperature_min,wave_height_max"


def _request(url: str, timeout: int = 30, retries: int = 3) -> dict | None:
    """Make a GET request to Open-Meteo. Returns parsed JSON.

    The free API rate-limits (HTTP 429) when our own test suite or grid
    queries fire many calls in a burst. Retry with backoff on 429 only —
    genuine robustness for the app, not just for tests.
    """
    import time as _time

    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ORCA-Marine-Intelligence/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                wait = 2 * (2 ** attempt)  # 2 s, 4 s, 8 s
                print(f"[OpenMeteo] 429 rate-limited — retry in {wait}s "
                      f"({attempt + 1}/{retries})", file=sys.stderr)
                _time.sleep(wait)
                continue
            raise


def get_sst_at_point(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> dict[str, Any] | None:
    """Fetch daily SST + wave summary at a single point.

    Args:
        lat: Latitude (e.g. 19.0 for Mumbai)
        lon: Longitude (e.g. 72.8 for Mumbai)
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD (inclusive, max 1 year back-to-front range)

    Returns:
        {
          "lat": float, "lon": float,
          "start_date": str, "end_date": str,
          "sst_max": float,  # warmest day in range (°C)
          "sst_min": float,  # coolest day in range (°C)
          "sst_mean": float, # average of all daily maxes
          "wave_max": float, # max wave height in range (m)
          "wave_mean": float,
          "n_days": int,
          "source": "Open-Meteo Marine API (MeteoFrance model)",
          "daily": [{"date": "2026-08-01", "sst_max": 28.5, "sst_min": 28.3, "wave_max": 2.86}, ...]
        }
    """
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "daily": DAILY_VARS,
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "auto",
    }
    url = f"{MARINE_API_URL}?{urllib.parse.urlencode(params)}"
    print(f"[OpenMeteo] Single point: ({lat:.2f}, {lon:.2f}) {start_date}..{end_date}", file=sys.stderr)

    try:
        data = _request(url)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        return {"error": f"HTTP {e.code}: {e.reason}", "details": body, "source": "Open-Meteo"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "source": "Open-Meteo"}

    if "error" in data:
        return {"error": data["error"], "source": "Open-Meteo"}

    daily_block = data.get("daily", {})
    times = daily_block.get("time", [])
    sst_max = daily_block.get("sea_surface_temperature_max", [])
    sst_min = daily_block.get("sea_surface_temperature_min", [])
    wave_max = daily_block.get("wave_height_max", [])

    daily = []
    for i, t in enumerate(times):
        daily.append({
            "date": t,
            "sst_max": sst_max[i] if i < len(sst_max) else None,
            "sst_min": sst_min[i] if i < len(sst_min) else None,
            "wave_max": wave_max[i] if i < len(wave_max) else None,
        })

    sst_max_vals = [d["sst_max"] for d in daily if d["sst_max"] is not None]
    sst_min_vals = [d["sst_min"] for d in daily if d["sst_min"] is not None]
    wave_vals = [d["wave_max"] for d in daily if d["wave_max"] is not None]

    def mean(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "lat": data.get("latitude", lat),
        "lon": data.get("longitude", lon),
        "requested_lat": lat,
        "requested_lon": lon,
        "start_date": start_date,
        "end_date": end_date,
        "sst_max": max(sst_max_vals) if sst_max_vals else None,
        "sst_min": min(sst_min_vals) if sst_min_vals else None,
        "sst_mean": mean(sst_max_vals),
        "wave_max": max(wave_vals) if wave_vals else None,
        "wave_mean": mean(wave_vals),
        "n_days": len(times),
        "source": "Open-Meteo Marine API (MeteoFrance, 0.08°)",
        "daily": daily,
    }


def get_sst_grid(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    start_date: str,
    end_date: str,
    step_deg: float = 0.5,
) -> dict[str, Any] | None:
    """Fetch SST + waves on a regular grid for map overlay.

    Open-Meteo supports comma-separated latitude / longitude lists, so
    we can ask for many points in one HTTP call (subject to a reasonable
    count; ~50-100 points per call is the practical sweet spot).

    For a 0.5° grid over a 2°×2° bbox:
      5 lat × 5 lon = 25 points (cheap, fast)
    For 0.25°:
      9 lat × 9 lon = 81 points (still cheap)
    For 0.1°:
      21 lat × 21 lon = 441 points (push it)

    Args:
        min_lat, max_lat: latitude range
        min_lon, max_lon: longitude range
        start_date, end_date: YYYY-MM-DD
        step_deg: grid step in degrees (0.5 = 0.5° ≈ 50 km)

    Returns:
        {
          "min_lat": ..., "max_lat": ..., "min_lon": ..., "max_lon": ...,
          "step_deg": float,
          "start_date": ..., "end_date": ...,
          "n_points": int,
          "points": [
            {"lat": 18.0, "lon": 72.0,
             "sst_max": 28.5, "sst_min": 28.3, "sst_mean": 28.4,
             "wave_max": 2.86, "wave_mean": 2.1,
             "n_days": 30},
            ...
          ],
          "source": "Open-Meteo Marine API"
        }
    """
    lats, lons = [], []
    lat = min_lat
    while lat <= max_lat + 1e-9:
        lats.append(round(lat, 4))
        lat += step_deg
    lon = min_lon
    while lon <= max_lon + 1e-9:
        lons.append(round(lon, 4))
        lon += step_deg

    n_pts = len(lats) * len(lons)
    if n_pts > 500:
        # Be nice to the free API. Callers should pick a coarser step
        # or split the bbox.
        return {
            "error": f"Grid too dense: {n_pts} points (max 500 per call).",
            "hint": f"step_deg={step_deg}, try a larger step.",
        }

    print(
        f"[OpenMeteo] Grid: {len(lats)} lat × {len(lons)} lon = {n_pts} points, "
        f"{start_date}..{end_date}",
        file=sys.stderr,
    )

    # Open-Meteo multi-location semantics: comma-separated latitude and
    # longitude lists are ZIP-PAIRED, not cross-multiplied — i.e.
    #   latitude=18,19&longitude=72,74 → (18,72) and (19,74) only.
    # To get a genuine 2-D grid we must enumerate every (lat, lon) pair
    # and repeat each coordinate at its pair position. (Found the hard
    # way: the old code sent the raw lists and got back 5 diagonal
    # points instead of a 5×5 grid.)
    pairs = [(la, lo) for la in lats for lo in lons]
    params = {
        "latitude": ",".join(f"{la:.4f}" for la, _lo in pairs),
        "longitude": ",".join(f"{lo:.4f}" for _la, lo in pairs),
        "daily": DAILY_VARS,
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "auto",
    }
    url = f"{MARINE_API_URL}?{urllib.parse.urlencode(params)}"

    try:
        data = _request(url, timeout=30)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        return {"error": f"HTTP {e.code}: {e.reason}", "details": body, "source": "Open-Meteo"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "source": "Open-Meteo"}

    # Open-Meteo MULTI-POINT response shape (verified by debug dump):
    #   [
    #     {
    #       "latitude": 18.04, "longitude": 71.96,
    #       "daily": {
    #         "time": ["2026-08-01", "2026-08-02", ...],
    #         "sea_surface_temperature_max": [28.6, 28.7, ...],
    #         "sea_surface_temperature_min": [28.5, 28.6, ...],
    #         "wave_height_max": [3.86, 3.76, ...],
    #       }
    #     },
    #     { "latitude": 18.54, "longitude": 72.46, "daily": {...}, "location_id": 1 },
    #     ...
    #   ]
    # i.e. a LIST of point-dicts. We just iterate, no row-major math needed.

    if not isinstance(data, list):
        # Defensive: handle single-point shape (dict) too, in case the
        # API ever returns that for a one-point grid request.
        if isinstance(data, dict):
            if "error" in data:
                return {"error": data["error"], "source": "Open-Meteo"}
            data = [data]
        else:
            return {
                "error": f"Unexpected response type: {type(data).__name__}",
                "source": "Open-Meteo",
            }

    if not data:
        return {"error": "Empty response from Open-Meteo", "source": "Open-Meteo"}

    def clean(vals):
        return [v for v in vals if v is not None] if isinstance(vals, list) else []

    points = []
    for pt in data:
        if not isinstance(pt, dict):
            continue
        if "error" in pt:
            # Sometimes Open-Meteo returns one errored point instead of failing the whole call
            continue
        la = pt.get("latitude")
        lo = pt.get("longitude")
        d = pt.get("daily", {}) or {}
        sst_max_vals = clean(d.get("sea_surface_temperature_max", []))
        sst_min_vals = clean(d.get("sea_surface_temperature_min", []))
        wave_vals = clean(d.get("wave_height_max", []))

        def mean(xs):
            return round(sum(xs) / len(xs), 2) if xs else None

        points.append({
            "lat": la,
            "lon": lo,
            "sst_max": max(sst_max_vals) if sst_max_vals else None,
            "sst_min": min(sst_min_vals) if sst_min_vals else None,
            "sst_mean": mean(sst_max_vals),
            "wave_max": max(wave_vals) if wave_vals else None,
            "wave_mean": mean(wave_vals),
            "n_days": len(d.get("time", []) or sst_max_vals),
        })

    if not points:
        return {
            "error": "No usable points in Open-Meteo response",
            "raw_count": len(data),
            "raw_preview": data[:1],
            "source": "Open-Meteo",
        }

    return {
        "min_lat": min_lat,
        "max_lat": max_lat,
        "min_lon": min_lon,
        "max_lon": max_lon,
        "step_deg": step_deg,
        "start_date": start_date,
        "end_date": end_date,
        "n_points": len(points),
        "points": points,
        "source": "Open-Meteo Marine API (MeteoFrance, 0.08°)",
    }


# Common Indian Ocean / coastal test points for quick demo
DEMO_POINTS = [
    {"name": "Mumbai offshore", "lat": 19.0, "lon": 72.8},
    {"name": "Goa offshore", "lat": 15.5, "lon": 73.7},
    {"name": "Cochin offshore", "lat": 9.5, "lon": 76.0},
    {"name": "Chennai offshore", "lat": 13.5, "lon": 80.5},
    {"name": "Visakhapatnam offshore", "lat": 17.5, "lon": 83.5},
    {"name": "Kandla/Gujarat offshore", "lat": 22.5, "lon": 68.5},
    {"name": "Andaman (Port Blair)", "lat": 12.0, "lon": 92.5},
    {"name": "Lakshadweep", "lat": 10.5, "lon": 72.5},
]


def demo_indian_ocean_sst(start_date: str | None = None,
                          end_date: str | None = None) -> list[dict[str, Any]]:
    """Fetch SST for all DEMO_POINTS in one pass and return list of results."""
    if end_date is None:
        end_date = (date.today() - timedelta(days=5)).isoformat()
    if start_date is None:
        start_date = (date.fromisoformat(end_date) - timedelta(days=30)).isoformat()

    out = []
    for p in DEMO_POINTS:
        r = get_sst_at_point(p["lat"], p["lon"], start_date, end_date)
        r["name"] = p["name"]
        out.append(r)
    return out
