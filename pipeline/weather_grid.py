"""Animated weather grid: multi-hour wind + humidity + temperature fields.

Feeds the zoom.earth-style live map (`frontend/weather_map.html`): ONE
Open-Meteo call returns an n×n grid of hourly frames so the frontend can
animate colours and advect wind particles without refetching.

Wire format notes (verified live 2026-09-13):
  - models=icon_global (bare "icon" is REJECTED by the API)
  - u/v components are NOT variables on this endpoint
    ("u_wind_component_10m" → HTTP 400); we request
    wind_speed_10m + wind_direction_10m with wind_speed_unit=ms and
    derive u = -s·sin(θ), v = -s·cos(θ) — the standard conversion,
    consistent with ORCA's compass convention (270 − atan2(v,u)) % 360.
  - multi-coordinate responses come back as a zip-paired LIST of
    location objects (same as humidity.py / fetch_met_grid).

The bundled demo snapshot (`pipeline.weather_demo_snapshot.py`) is REAL
ICON output, served when ?demo=1 — used by the frontend as an honest
offline fallback (clearly labelled) when the live API is unreachable.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from typing import Any, Callable

from pipeline.humidity import _grid_pairs, legend
from pipeline.ttlcache import cached

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "ORCA-ps176/0.1 (SIH 2026)"
MODEL = "icon_global"
HOURLY = "wind_speed_10m,wind_direction_10m,relative_humidity_2m,temperature_2m"
FRAMES_MAX = 25          # 24 h ahead + current hour
GRID_N_MAX = 16          # 256 points — still one call
SPAN_MAX_DEG = 30.0


def _http_json(url: str, params: dict[str, str], timeout: float = 25.0):
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _fetch_grid(pairs: list[tuple[float, float]], frames: int) -> list[dict]:
    """One Open-Meteo call for the whole grid × all frames."""
    lats = ",".join(f"{p[0]:.4f}" for p in pairs)
    lons = ",".join(f"{p[1]:.4f}" for p in pairs)
    payload = _http_json(FORECAST_URL, {
        "latitude": lats,
        "longitude": lons,
        "hourly": HOURLY,
        "models": MODEL,
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "forecast_hours": str(frames),
    })
    return payload if isinstance(payload, list) else [payload]


def _pick(row: dict, hour: int, key: str) -> float | None:
    vals = (row.get("hourly") or {}).get(key) or []
    if hour >= len(vals) or not isinstance(vals[hour], (int, float)):
        return None
    return float(vals[hour])


def _uv(speed_ms: float | None, dir_deg: float | None) -> tuple[float | None, float | None]:
    if speed_ms is None or dir_deg is None:
        return None, None
    th = math.radians(dir_deg)
    return round(-speed_ms * math.sin(th), 2), round(-speed_ms * math.cos(th), 2)


def get_weather_grid(
    lat: float,
    lon: float,
    span: float = 3.0,
    frames: int = 8,
    grid_n: int = 9,
    _fetcher: Callable[[list[tuple[float, float]], int], list[dict]] | None = None,
) -> dict[str, Any]:
    """Compact multi-frame grid. Never raises for data problems — honest
    error dict, same contract as every other ORCA source."""
    span = min(max(span, 0.25), SPAN_MAX_DEG)
    frames = min(max(int(frames), 2), FRAMES_MAX)
    grid_n = int(min(max(grid_n, 3), GRID_N_MAX))

    def _build() -> dict[str, Any]:
        import datetime as _dt

        pairs = _grid_pairs(lat, lon, span, grid_n)
        try:
            rows = (_fetcher or _fetch_grid)(pairs, frames)
        except Exception as exc:  # noqa: BLE001
            return {"type": "weather_grid", "error":
                    f"ICON weather-grid fetch failed: {type(exc).__name__}: {exc}",
                    "source": "Open-Meteo (DWD ICON)"}
        if not isinstance(rows, list) or len(rows) != len(pairs):
            return {"type": "weather_grid", "error":
                    f"Open-Meteo returned {len(rows) if isinstance(rows, list) else 0} "
                    f"locations for {len(pairs)} grid points",
                    "source": "Open-Meteo (DWD ICON)"}

        times = ((rows[0].get("hourly") or {}).get("time") or [])[:frames]
        n_f = len(times) or 1
        u: list[list] = [[] for _ in range(n_f)]
        v: list[list] = [[] for _ in range(n_f)]
        rh: list[list] = [[] for _ in range(n_f)]
        temp: list[list] = [[] for _ in range(n_f)]
        for row in rows:
            for h in range(n_f):
                cu, cv = _uv(_pick(row, h, "wind_speed_10m"),
                             _pick(row, h, "wind_direction_10m"))
                u[h].append(cu)
                v[h].append(cv)
                r_ = _pick(row, h, "relative_humidity_2m")
                t_ = _pick(row, h, "temperature_2m")
                rh[h].append(round(r_) if r_ is not None else None)
                temp[h].append(round(t_, 1) if t_ is not None else None)

        return {
            "type": "weather_grid",
            "demo": False,
            "fetched_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "model": f"{MODEL} (DWD ICON global) via Open-Meteo — the model zoom.earth's humidity map displays",
            "source": "https://open-meteo.com/ (DWD ICON, CC-BY-4.0)",
            "center": {"lat": lat, "lon": lon},
            "span_deg": span,
            "grid_n": grid_n,
            "step_deg": round(span / (grid_n - 1), 4),
            "times": times,
            "lats": [round(p[0], 4) for p in pairs[::grid_n]],   # descending (N→S)
            "lons": [round(p[1], 4) for p in pairs[:grid_n]],    # ascending (W→E)
            "u": u, "v": v, "rh": rh, "temp": temp,
            "legend": legend(),
        }

    return cached(f"weathergrid:{lat:.1f}:{lon:.1f}:{span:.2f}:{frames}:{grid_n}",
                  1800, _build)


if __name__ == "__main__":  # live smoke check (needs network)
    d = get_weather_grid(22.2, 69.4, 3.0, frames=8, grid_n=9)
    if d.get("error"):
        print("ERROR:", d["error"])
    else:
        print(f"frames={len(d['times'])} points={len(d['u'][0])} "
              f"times {d['times'][0]}..{d['times'][-1]}")
