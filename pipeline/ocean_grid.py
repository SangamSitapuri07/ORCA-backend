"""Ocean grid — satellite currents + sea-surface temperature + wave forecast.

One compact payload for the animated sea layers of the live weather map:

  * currents  — NOAA CoastWatch BLENDED NRT geostrophic currents
                (altimetry: Sentinel-3A/B, CryoSat2, Jason-2/3, SARAL/AltiKa)
                `noaacwBLENDEDNRTcurrentsDaily`, 0.25°, daily, ~3-day NRT lag
  * SST       — NOAA Coral Reef Watch CoralTemp
                `noaacrwsstDaily`, 0.05° native (sampled at 0.25°), daily
  * waves     — Open-Meteo Marine API (DWD-style marine model), hourly

All three are free, no-login, public APIs. Native cells are bilinearly
interpolated server-side onto the same grid_n x grid_n lattice the weather
grid uses, so the frontend renders both with one code path. Land cells are
null in the source data and stay null here — that IS the coastline mask;
nothing is ever fabricated.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Callable

from pipeline.ttlcache import cached
from pipeline.weather_grid import FRAMES_MAX, GRID_N_MAX, SPAN_MAX_DEG, _grid_pairs

ERDDAP = "https://coastwatch.noaa.gov/erddap/griddap"
CUR_DS = "noaacwBLENDEDNRTcurrentsDaily"   # u_current, v_current (m/s)
SST_DS = "noaacrwsstDaily"                 # analysed_sst (°C)
MARINE = "https://marine-api.open-meteo.com/v1/marine"

SOURCES = {
    "currents": {
        "model": "NOAA CoastWatch blended geostrophic currents "
                 "(altimetry: Sentinel-3A/B, CryoSat2, Jason-2/3, SARAL/AltiKa)",
        "source": "https://coastwatch.noaa.gov/erddap/griddap/noaacwBLENDEDNRTcurrentsDaily",
    },
    "sst": {
        "model": "NOAA Coral Reef Watch CoralTemp satellite SST",
        "source": "https://coastwatch.noaa.gov/erddap/griddap/noaacrwsstDaily",
    },
    "waves": {
        "model": "Open-Meteo Marine API wave model",
        "source": "https://open-meteo.com/ (Marine API, CC-BY-4.0)",
    },
}


def _get_json(url: str, timeout: float = 30.0) -> Any:
    with urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "ORCA-backend/0.2 (+marine layer)"}),
            timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _brack(s: str) -> str:
    """ERDDAP dimension constraints use [ ] which must be percent-encoded."""
    return s.replace("[", "%5B").replace("]", "%5D")


def currents_url(lat_t: float, lat_b: float, lon_l: float, lon_r: float) -> str:
    q = (f"u_current[(last)][({lat_b}):1:({lat_t})][({lon_l}):1:({lon_r})],"
         f"v_current[(last)][({lat_b}):1:({lat_t})][({lon_l}):1:({lon_r})]")
    return f"{ERDDAP}/{CUR_DS}.json?{_brack(q)}"


def sst_url(lat_t: float, lat_b: float, lon_l: float, lon_r: float) -> str:
    q = f"analysed_sst[(last)][({lat_b}):5:({lat_t})][({lon_l}):5:({lon_r})]"
    return f"{ERDDAP}/{SST_DS}.json?{_brack(q)}"


def waves_url(pairs: list[tuple[float, float]], frames: int) -> str:
    p = urllib.parse.urlencode({
        "latitude": ",".join(f"{la:.4f}" for la, _ in pairs),
        "longitude": ",".join(f"{lo:.4f}" for _, lo in pairs),
        "hourly": "wave_height,wave_direction,wave_period",
        "timezone": "UTC",
        "forecast_hours": str(frames + 2),
    })
    return f"{MARINE}?{p}"


# ── ERDDAP table JSON → nested grid {lat: {lon: value}} ──
def _parse_erddap(payload: Any, val_idx: int) -> tuple[dict[float, dict[float, Any]], str | None]:
    rows = ((payload or {}).get("table") or {}).get("rows") or []
    grid: dict[float, dict[float, Any]] = {}
    time = None
    for row in rows:
        if not isinstance(row, list) or len(row) <= val_idx:
            continue
        la, lo, val = row[1], row[2], row[val_idx]
        grid.setdefault(round(float(la), 4), {})[round(float(lo), 4)] = (
            None if val is None else float(val))
        time = time or row[0]
    return grid, time


def _interp(grid: dict[float, dict[float, Any]], lats: list[float],
            lons: list[float], lat: float, lon: float) -> float | None:
    """Bilinear on the native cell centres; null-aware (coastline)."""
    if not grid or not lats or not lons:
        return None
    if lat > lats[0] + 1e-9 or lat < lats[-1] - 1e-9:
        return None
    if lon < lons[0] - 1e-9 or lon > lons[-1] + 1e-9:
        return None
    r = 0
    while r < len(lats) - 2 and lat < lats[r + 1]:
        r += 1
    c = 0
    while c < len(lons) - 2 and lon > lons[c + 1]:
        c += 1
    row0, row1 = grid.get(lats[r], {}), grid.get(lats[r + 1], {})
    corners = [(row0.get(lons[c]), lats[r], lons[c]),
               (row0.get(lons[c + 1]), lats[r], lons[c + 1]),
               (row1.get(lons[c]), lats[r + 1], lons[c]),
               (row1.get(lons[c + 1]), lats[r + 1], lons[c + 1])]
    if any(v is None for v, _, _ in corners):
        live = [(v, la, lo) for v, la, lo in corners if v is not None]
        if not live:
            return None
        # coastal cell: nearest valid corner (never invent a gradient)
        return min(live, key=lambda t: (t[1] - lat) ** 2 + (t[2] - lon) ** 2)[0]
    fy = (lats[r] - lat) / (lats[r] - lats[r + 1])
    fx = (lon - lons[c]) / (lons[c + 1] - lons[c])
    fy = min(max(fy, 0.0), 1.0)
    fx = min(max(fx, 0.0), 1.0)
    return (corners[0][0] * (1 - fx) * (1 - fy) + corners[1][0] * fx * (1 - fy)
            + corners[2][0] * (1 - fx) * fy + corners[3][0] * fx * fy)


def _sample(grid: dict[float, dict[float, Any]], pairs) -> list[float | None]:
    if not grid:
        return [None] * len(pairs)
    lats = sorted(grid, reverse=True)
    lons = sorted(next(iter(grid.values())))
    return [_interp(grid, lats, lons, la, lo) for la, lo in pairs]


def wave_legend() -> list[dict[str, Any]]:
    return [
        {"value": 0, "color": "#1B4F72", "label": "calm"},
        {"value": 0.5, "color": "#2E86C1", "label": "0.5 m"},
        {"value": 1.0, "color": "#48C9B0", "label": "1 m"},
        {"value": 1.5, "color": "#F4D03F", "label": "1.5 m"},
        {"value": 2.0, "color": "#E67E22", "label": "2 m"},
        {"value": 3.0, "color": "#B03A2E", "label": "3 m"},
        {"value": 4.0, "color": "#641E16", "label": "4 m+"},
    ]


def get_ocean_grid(
    lat: float,
    lon: float,
    span: float = 3.0,
    frames: int = 8,
    grid_n: int = 9,
    _fetch: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Compact sea grid: currents + SST (daily satellite) and waves (hourly
    forecast) on the weather-grid lattice. Errors are honest per-source
    dicts; land cells are null; nothing is fabricated."""
    import datetime as _dt

    span = min(max(span, 0.25), SPAN_MAX_DEG)
    frames = min(max(int(frames), 2), FRAMES_MAX)
    grid_n = int(min(max(grid_n, 3), GRID_N_MAX))
    fetch = _fetch or _get_json

    def _build() -> dict[str, Any]:
        pairs = _grid_pairs(lat, lon, span, grid_n)
        half = span / 2 + 0.3                      # margin ≥ one native cell
        lat_t, lat_b = lat + half, lat - half
        lon_l, lon_r = lon - half, lon + half
        errors: dict[str, str] = {}

        # ── currents (satellite altimetry, daily; u and v in ONE response) ──
        cu: list = [None] * len(pairs)
        cv: list = [None] * len(pairs)
        cur_time = None
        try:
            rows = ((fetch(currents_url(lat_t, lat_b, lon_l, lon_r)) or {})
                    .get("table") or {}).get("rows") or []
            gu: dict[float, dict[float, Any]] = {}
            gv: dict[float, dict[float, Any]] = {}
            for row in rows:
                if not isinstance(row, list) or len(row) < 5:
                    continue
                la, lo = round(float(row[1]), 4), round(float(row[2]), 4)
                u, v = row[3], row[4]
                gu.setdefault(la, {})[lo] = None if u is None else float(u)
                gv.setdefault(la, {})[lo] = None if v is None else float(v)
                cur_time = cur_time or row[0]
            uu = _sample(gu, pairs)
            vv = _sample(gv, pairs)
            cu = [None if v is None else round(v, 3) for v in uu]
            cv = [None if v is None else round(v, 3) for v in vv]
        except Exception as exc:  # noqa: BLE001
            errors["currents"] = f"{type(exc).__name__}: {exc}"

        # ── SST (satellite, daily) ──
        sst: list = [None] * len(pairs)
        sst_time = None
        try:
            gs, sst_time = _parse_erddap(fetch(sst_url(lat_t, lat_b, lon_l, lon_r)), 3)
            sst = [None if v is None else round(v, 1) for v in _sample(gs, pairs)]
        except Exception as exc:  # noqa: BLE001
            errors["sst"] = f"{type(exc).__name__}: {exc}"

        # ── waves (hourly forecast; land → null) ──
        wave_times: list[str] = []
        wh: list = []
        wd: list = []
        wp: list = []
        try:
            rows = fetch(waves_url(pairs, frames))
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list) or len(rows) != len(pairs):
                raise ValueError(f"marine API returned {len(rows) if isinstance(rows, list) else 0}"
                                 f" locations for {len(pairs)} points")
            times = ((rows[0].get("hourly") or {}).get("time") or [])[:frames]
            n_f = len(times) or 1
            wh = [[] for _ in range(n_f)]
            wd = [[] for _ in range(n_f)]
            wp = [[] for _ in range(n_f)]
            for row in rows:
                h = row.get("hourly") or {}
                for i in range(n_f):
                    def g_(name):
                        vals = h.get(name) or []
                        return vals[i] if i < len(vals) else None
                    wh[i].append(None if g_("wave_height") is None
                                 else round(float(g_("wave_height")), 2))
                    wd[i].append(None if g_("wave_direction") is None
                                 else int(g_("wave_direction")))
                    wp[i].append(None if g_("wave_period") is None
                                 else round(float(g_("wave_period")), 1))
            wave_times = times
        except Exception as exc:  # noqa: BLE001
            errors["waves"] = f"{type(exc).__name__}: {exc}"

        if errors and cu[0] is None and sst[0] is None and not wh:
            return {"type": "ocean_grid",
                    "error": "; ".join(f"{k}: {v}" for k, v in errors.items()),
                    "source": "NOAA CoastWatch ERDDAP + Open-Meteo Marine"}

        return {
            "type": "ocean_grid",
            "demo": False,
            "fetched_at": _dt.datetime.now(_dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S+00:00"),
            "sources": {
                "currents": {**SOURCES["currents"], "time": cur_time},
                "sst": {**SOURCES["sst"], "time": sst_time},
                "waves": {**SOURCES["waves"], "time": wave_times[0] if wave_times else None},
            },
            "errors": errors,
            "center": {"lat": lat, "lon": lon},
            "span_deg": span,
            "grid_n": grid_n,
            "step_deg": round(span / (grid_n - 1), 4),
            "lats": [round(p[0], 4) for p in pairs[::grid_n]],   # descending
            "lons": [round(p[1], 4) for p in pairs[:grid_n]],    # ascending
            "cu": cu, "cv": cv,          # m/s, single daily frame
            "sst": sst,                  # °C, single daily frame
            "times": wave_times,         # wave frames, hourly UTC
            "wh": wh, "wd": wd, "wp": wp,   # [frame][point], null on land
            "wave_legend": wave_legend(),
        }

    return cached(f"oceangrid:{lat:.1f}:{lon:.1f}:{span:.2f}:{frames}:{grid_n}",
                  1800, _build)
