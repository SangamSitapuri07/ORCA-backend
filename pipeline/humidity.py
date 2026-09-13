"""Humidity map field — the zoom.earth-style RH layer, rebuilt first-party.

What zoom.earth's humidity map (…/maps/humidity/#view=…&model=icon)
displays is **relative humidity at 2 m from DWD's ICON model**. zoom.earth
itself has no public tile/map API — scraping their rendered tiles would
be fragile and against their terms. The honest ORCA way: fetch the SAME
underlying model from Open-Meteo (free, no key, `models=icon`) on a grid
and let our own UI paint it.

    GET /api/v1/humidity?lat=22.2&lon=69.4&span=12&hours=0

  → an n×n grid of {lat, lon, rh_pct, temp_c, dew_point_c,
    dew_depression_c, land, color} plus a ready-to-draw legend palette.
    ONE Open-Meteo call per grid (comma-separated coordinate lists — the
    API zip-pairs them, so we send the full cartesian pair list; lesson
    learned 2026-09-03 with get_sst_grid).

Time slider support: `hours` = forecast hours ahead (0–48); each hour
has its own cached fetch. RH is a smooth field — a 9×9 or 12×12 grid
bilinearly interpolated by the frontend looks exactly like the zoom.earth
render at city-to-country scale.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from pipeline.ttlcache import cached

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "ORCA-ps176/0.1 (SIH 2026)"

MODEL = "icon_global"    # Open-Meteo's enum for DWD ICON global (~11 km) — the
                         # model zoom.earth's humidity map calls "icon". NOTE:
                         # bare "icon" is REJECTED by the API ("Cannot
                         # initialize MultiDomains") — verified live 2026-09-13;
                         # valid names: icon_global, icon_seamless, icon_eu, icon_d2.
GRID_N = 9               # 9×9 = 81 points per call (matches fetch_met_grid)
GRID_N_MAX = 16          # 256 points — still one call, ~1 MB response worst case
SPAN_MAX_DEG = 30.0
HOURS_MAX = 48
CACHE_TTL_SEC = 1800     # ICON updates 4×/day; 30 min keeps demos snappy

# Relative-humidity palette (0–100 %). Style follows the common met
# convention (dry = warm oranges, moist = greens → teal/blue) so it reads
# like zoom.earth/Ventusky. Stops are (rh %, hex); values between stops
# are linearly interpolated in RGB. Tune to taste — the legend is
# generated from this table, so the map and legend can never disagree.
PALETTE: list[tuple[int, str]] = [
    (0,   "#B3541E"),   # bone-dry
    (20,  "#E67E22"),   # dry
    (40,  "#F4D03F"),   # low
    (60,  "#A9DF72"),   # moderate
    (75,  "#58D68D"),   # humid
    (85,  "#2E9E8F"),   # very humid
    (100, "#1A5276"),   # saturated
]

_LEGEND_LABELS = {
    0: "very dry", 20: "dry", 40: "low", 60: "moderate",
    75: "humid", 85: "very humid", 100: "saturated",
}


# ── palette helpers ───────────────────────────────────────────────────

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def color_for_rh(rh: float) -> str:
    """Hex colour for an RH percentage, interpolated between palette stops."""
    if rh is None or not isinstance(rh, (int, float)):
        return "#808080"                       # unknown → honest grey
    rh = max(0.0, min(100.0, float(rh)))
    for (r0, c0), (r1, c1) in zip(PALETTE, PALETTE[1:]):
        if rh <= r1:
            if rh <= r0:
                return c0
            t = (rh - r0) / (r1 - r0)
            a, b = _hex_to_rgb(c0), _hex_to_rgb(c1)
            return "#{:02X}{:02X}{:02X}".format(
                round(a[0] + (b[0] - a[0]) * t),
                round(a[1] + (b[1] - a[1]) * t),
                round(a[2] + (b[2] - a[2]) * t),
            )
    return PALETTE[-1][1]


def legend() -> list[dict[str, Any]]:
    return [
        {"value": r, "color": c, "label": f"{r}% ({_LEGEND_LABELS.get(r, '')})".strip()}
        for r, c in PALETTE
    ]


# ── grid + fetch ──────────────────────────────────────────────────────

def _grid_pairs(lat: float, lon: float, span: float, n: int) -> list[tuple[float, float]]:
    """Cartesian lat×lon pairs across the box (row-major, north→south)."""
    half = span / 2.0
    lat_step = span / (n - 1)
    lon_step = span / (n - 1)
    pts = []
    for i in range(n):
        for j in range(n):
            pts.append((
                round(lat + half - i * lat_step, 4),
                round(lon - half + j * lon_step, 4),
            ))
    return pts


def _http_json(url: str, params: dict[str, str], timeout: float = 20.0):
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch_icon_grid(pairs: list[tuple[float, float]], hours_ahead: int) -> list[dict]:
    """One Open-Meteo call for the whole grid; returns per-location dicts."""
    lats = ",".join(f"{p[0]:.4f}" for p in pairs)
    lons = ",".join(f"{p[1]:.4f}" for p in pairs)
    payload = _http_json(FORECAST_URL, {
        "latitude": lats,
        "longitude": lons,
        "hourly": "relative_humidity_2m,temperature_2m,dew_point_2m",
        "models": MODEL,
        "timezone": "UTC",
        "forecast_hours": str(hours_ahead + 1),
    })
    # multi-coordinate responses come back as a LIST of location objects
    # (zip-paired with our coordinate lists); a single identical pair can
    # come back as one plain dict — normalise both.
    if isinstance(payload, list):
        return payload
    return [payload]


def _pick_hour(series: dict, hours_ahead: int, key: str) -> float | None:
    vals = (series.get("hourly") or {}).get(key) or []
    if not vals:
        return None
    idx = min(hours_ahead, len(vals) - 1)
    v = vals[idx]
    return round(float(v), 2) if isinstance(v, (int, float)) else None


def _valid_time(series: dict, hours_ahead: int) -> str | None:
    t = ((series.get("hourly") or {}).get("time") or [])
    if not t:
        return None
    return t[min(hours_ahead, len(t) - 1)]


def get_humidity_field(
    lat: float,
    lon: float,
    span: float = 3.0,
    hours_ahead: int = 0,
    grid_n: int = GRID_N,
    _fetcher: Callable[[list[tuple[float, float]], int], list[dict]] | None = None,
) -> dict[str, Any]:
    """Relative-humidity grid at 2 m from DWD ICON (via Open-Meteo).

    Never raises for data problems — returns an honest error dict, so the
    API layer can surface the real reason (timeout, rate limit, outage)
    exactly like every other ORCA source.
    """
    span = min(max(span, 0.25), SPAN_MAX_DEG)
    hours_ahead = min(max(hours_ahead, 0), HOURS_MAX)
    grid_n = int(min(max(grid_n, 3), GRID_N_MAX))

    def _build() -> dict[str, Any]:
        from pipeline import landmask
        pairs = _grid_pairs(lat, lon, span, grid_n)
        try:
            rows = (_fetcher or _fetch_icon_grid)(pairs, hours_ahead)
        except Exception as exc:  # noqa: BLE001
            return {
                "type": "humidity",
                "error": f"ICON humidity fetch failed: {type(exc).__name__}: {exc}",
                "source": "Open-Meteo (DWD ICON)",
            }
        if not isinstance(rows, list) or len(rows) != len(pairs):
            return {
                "type": "humidity",
                "error": (f"Open-Meteo returned {len(rows) if isinstance(rows, list) else 0} "
                          f"locations for {len(pairs)} grid points"),
                "source": "Open-Meteo (DWD ICON)",
            }

        points = []
        for (p_lat, p_lon), row in zip(pairs, rows):
            rh = _pick_hour(row, hours_ahead, "relative_humidity_2m")
            temp = _pick_hour(row, hours_ahead, "temperature_2m")
            dew = _pick_hour(row, hours_ahead, "dew_point_2m")
            points.append({
                "lat": p_lat,
                "lon": p_lon,
                "rh_pct": rh,
                "temp_c": temp,
                "dew_point_c": dew,
                "dew_depression_c": round(temp - dew, 2)
                if isinstance(temp, (int, float)) and isinstance(dew, (int, float)) else None,
                # real GLOBE 1 km land check — coastal cells stay marked
                "land": landmask.is_land(p_lat, p_lon),
                "color": color_for_rh(rh),
            })

        valid = _valid_time(rows[0], hours_ahead) if rows else None
        rh_values = [p["rh_pct"] for p in points if p["rh_pct"] is not None]
        return {
            "type": "humidity",
            "model": f"{MODEL} (DWD ICON global) via Open-Meteo — the model zoom.earth's humidity map displays",
            "center": {"lat": lat, "lon": lon},
            "span_deg": span,
            "grid_n": grid_n,
            "step_deg": round(span / (grid_n - 1), 4),
            "hours_ahead": hours_ahead,
            "valid_time": valid,
            "n_points": len(points),
            "points": points,
            "summary": {
                "rh_min": round(min(rh_values), 1) if rh_values else None,
                "rh_max": round(max(rh_values), 1) if rh_values else None,
                "rh_mean": round(sum(rh_values) / len(rh_values), 1) if rh_values else None,
            },
            "legend": legend(),
            "palette_note": "Tune PALETTE in pipeline/humidity.py to match the exact zoom.earth shades.",
            "source": "Open-Meteo (DWD ICON), free, no key",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    key = f"humidity:{lat:.1f}:{lon:.1f}:{span:.1f}:{hours_ahead}:{grid_n}"
    return cached(key, CACHE_TTL_SEC, _build)


if __name__ == "__main__":
    # quick live check: the Kutch view from the zoom.earth link
    d = get_humidity_field(22.2, 69.4, span=12.0, hours_ahead=0)
    if d.get("error"):
        print("ERROR:", d["error"], file=sys.stderr)
        sys.exit(1)
    print(f"{d['n_points']} pts · valid {d['valid_time']} · "
          f"RH {d['summary']['rh_min']}–{d['summary']['rh_max']}% (mean {d['summary']['rh_mean']}%)")
    for p in d["points"][:: max(1, len(d["points"]) // 8)]:
        print(f"  ({p['lat']:.2f},{p['lon']:.2f}) RH {p['rh_pct']}% "
              f"T {p['temp_c']}°C dew {p['dew_point_c']}°C {p['color']}"
              + (" [land]" if p["land"] else ""))
