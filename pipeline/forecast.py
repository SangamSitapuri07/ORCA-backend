"""Hourly point forecast for one ocean location — waves, wind, current, rain.

Two free, no-key Open-Meteo endpoints, both requested in UTC so their
hourly time axes align perfectly:

  marine:   https://marine-api.open-meteo.com/v1/marine
            → wave_height, swell_wave_height, ocean_current_velocity ...
            (waves in metres, current in m/s → converted to knots)
  forecast: https://api.open-meteo.com/v1/forecast
            → wind_speed_10m, wind_gusts_10m, precipitation
            (requested directly in knots via wind_speed_unit=kn)

Knots (kn) = nautical miles per hour; the unit IMD and every fisher uses
(1 kn = 1.852 km/h). We convert currents from m/s (1 m/s ≈ 1.944 kn).

Used by: advisory card (variables + safe window), alerts engine, chat.
"""
from __future__ import annotations

import bisect
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pipeline.ttlcache import cached

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "ORCA/1.0 (SIH 2026; marine research)"
TTL_SEC = 30 * 60
MS_TO_KN = 1.943844


def _http_json(url: str, params: dict[str, str], timeout: float = 12.0) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_now(lat: float, lon: float, days: int) -> dict[str, Any]:
    marine = _http_json(MARINE_URL, {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": ("wave_height,swell_wave_height,ocean_current_velocity,"
                   "ocean_current_direction,sea_surface_temperature"),
        "forecast_days": str(days),
        "timezone": "UTC",
    })
    weather = _http_json(FORECAST_URL, {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": "wind_speed_10m,wind_gusts_10m,precipitation",
        "forecast_days": str(days),
        "wind_speed_unit": "kn",
        "timezone": "UTC",
    })
    mh = marine.get("hourly", {})
    wh = weather.get("hourly", {})
    times = mh.get("time", []) or wh.get("time", [])
    n = len(times)

    def col(src: dict, key: str) -> list:
        v = src.get(key) or []
        return (v + [None] * n)[:n]

    current_kn = [
        (None if v is None else round(v * MS_TO_KN, 2))
        for v in col(mh, "ocean_current_velocity")
    ]

    hourly = {
        "time": times,
        "wave_height_m": col(mh, "wave_height"),
        "swell_height_m": col(mh, "swell_wave_height"),
        "current_kn": current_kn,
        "current_dir_deg": col(mh, "ocean_current_direction"),
        "sst_c": col(mh, "sea_surface_temperature"),
        "wind_kn": col(wh, "wind_speed_10m"),
        "gust_kn": col(wh, "wind_gusts_10m"),
        "rain_mm": col(wh, "precipitation"),
    }
    return {
        "source": "Open-Meteo Marine + Forecast (MeteoFrance/ECMWF models)",
        "lat": lat,
        "lon": lon,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hourly": hourly,
    }


def get_point_forecast(lat: float, lon: float, days: int = 4, force: bool = False) -> dict[str, Any]:
    """Hourly forecast arrays (cached 30 min per 0.25° cell)."""
    key = f"forecast:{lat:.2f}:{lon:.2f}:{days}"
    if force:
        from pipeline import ttlcache
        with ttlcache._lock:
            ttlcache._store.pop(key, None)
    data = cached(key, TTL_SEC, lambda: _fetch_now(lat, lon, days))
    return _summarize(data)


def _now_index(times: list[str]) -> int:
    """Index of the current (or nearest past) hour in a UTC time list."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    return max(0, bisect.bisect_right(times, now_iso) - 1)


def _max_of(arr: list, lo: int, span: int) -> float | None:
    vals = [v for v in arr[lo:lo + span] if v is not None]
    return max(vals) if vals else None


def _summarize(data: dict[str, Any]) -> dict[str, Any]:
    h = data["hourly"]
    times = h["time"]
    if not times:
        return {**data, "now": {}, "next24h": {}, "next48h": {}}
    i = _now_index(times)

    def now(key: str):
        col = h.get(key) or []
        return col[i] if i < len(col) else None

    out = dict(data)
    out["now"] = {
        "time": times[min(i, len(times) - 1)] + "Z",
        "wave_height_m": now("wave_height_m"),
        "swell_height_m": now("swell_height_m"),
        "current_kn": now("current_kn"),
        "current_dir_deg": now("current_dir_deg"),
        "sst_c": now("sst_c"),
        "wind_kn": now("wind_kn"),
        "gust_kn": now("gust_kn"),
        "rain_mm": now("rain_mm"),
    }
    for span, label in ((24, "next24h"), (48, "next48h")):
        out[label] = {
            "wave_max_m": _max_of(h["wave_height_m"], i, span),
            "swell_max_m": _max_of(h["swell_height_m"], i, span),
            "wind_max_kn": _max_of(h["wind_kn"], i, span),
            "gust_max_kn": _max_of(h["gust_kn"], i, span),
            "rain_total_mm": (
                None if all(v is None for v in h["rain_mm"][i:i + span])
                else round(sum(v or 0 for v in h["rain_mm"][i:i + span]), 1)
            ),
        }
    return out


def chart_series(forecast: dict[str, Any], hours: int = 48, step: int = 3) -> dict[str, Any]:
    """Downsampled hourly series for UI charts (next `hours` hours).

    Same real arrays the advisory verdict uses — every chart the user
    sees is literally the evidence the verdict was built from: waves,
    swell, wind, gusts, surface current, sea-surface temperature, rain.
    """
    empty = {"labels": [], "wave_m": [], "swell_m": [], "wind_kn": [],
             "gust_kn": [], "current_kn": [], "sst_c": [], "rain_mm": []}
    h = forecast.get("hourly", {})
    times = h.get("time", [])
    if not times:
        return empty
    i = _now_index(times)
    end = min(len(times), i + hours)
    idx = list(range(i, end, step))

    def take(key: str) -> list:
        col = h.get(key) or []
        return [col[k] if k < len(col) else None for k in idx]

    return {
        "labels": [times[k][5:] for k in idx],  # "MM-DDTHH:MM"
        "wave_m": take("wave_height_m"),
        "swell_m": take("swell_height_m"),
        "wind_kn": take("wind_kn"),
        "gust_kn": take("gust_kn"),
        "current_kn": take("current_kn"),
        "sst_c": take("sst_c"),
        "rain_mm": take("rain_mm"),
    }


def find_safe_window(
    forecast: dict[str, Any],
    wave_ok_m: float = 2.5,
    wind_ok_kn: float = 20.0,
    gust_ok_kn: float = 30.0,
    min_hours: int = 3,
    horizon_hours: int = 72,
) -> dict[str, Any]:
    """First contiguous stretch (≥ min_hours) where a small boat is safe:
    waves < 2.5 m AND sustained wind < 20 kn AND gusts < 30 kn.

    Thresholds follow WMO/IMD small-craft practice:
      - ~20 kn ≈ fresh breeze (Beaufort 5) — workable but tiring
      - 2.5 m — common small-vessel wave caution level in INCOIS bulletins
    Returns {"from","to","hours"} in UTC, or None values with a note.
    """
    h = forecast.get("hourly", {})
    times = h.get("time", [])
    if not times:
        return {"found": False, "note": "No forecast timeline available."}
    start = _now_index(times)

    run_start = None
    for k in range(start, min(len(times), start + horizon_hours)):
        w = h["wave_height_m"][k] if k < len(h["wave_height_m"]) else None
        wd = h["wind_kn"][k] if k < len(h["wind_kn"]) else None
        g = h["gust_kn"][k] if k < len(h["gust_kn"]) else None
        ok = (
            (w is None or w < wave_ok_m)
            and (wd is None or wd < wind_ok_kn)
            and (g is None or g < gust_ok_kn)
        )
        if ok and run_start is None:
            run_start = k
        if not ok and run_start is not None:
            if k - run_start >= min_hours:
                return {
                    "found": True,
                    "from_utc": times[run_start] + "Z",
                    "to_utc": times[k] + "Z",
                    "hours": k - run_start,
                }
            run_start = None
    end = min(len(times), start + horizon_hours)
    if run_start is not None and end - run_start >= min_hours:
        return {
            "found": True,
            "from_utc": times[run_start] + "Z",
            "to_utc": times[end - 1] + "Z",
            "hours": end - run_start,
            "note": "Window extends to the end of the forecast horizon.",
        }
    return {"found": False, "note": f"No {min_hours}h+ safe stretch in the next {horizon_hours}h."}
