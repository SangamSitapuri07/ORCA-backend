# Humidity Map (zoom.earth-style RH layer) — ORCA-backend

**Status:** live · **Endpoint:** `GET /api/v1/humidity` · **Model:** DWD ICON global (~11 km) via Open-Meteo (`models=icon_global`) · **Auth:** none needed

The user's reference: `zoom.earth/maps/humidity/#view=22.2,69.4,4.2z/model=icon` — a
relative-humidity map over Kutch/Gujarat driven by the DWD ICON model.

## Why we don't just use zoom.earth's map

zoom.earth renders its own tiles; it has **no public tile/map API**, and proxying or
scraping their rendered tiles is fragile and against their terms. But the *data*
underneath is DWD's ICON model — which Open-Meteo serves **free, keyless, for any
point on Earth**. So ORCA rebuilds the same layer first-party: same model, our own
grid, our own palette. (This is also the honest-sourcing rule: every number we serve
is traceable to a named source, never fabricated.)

## The one live gotcha: `icon` vs `icon_global`

Open-Meteo **rejects** `models=icon` with
`{"reason":"Invalid value: Cannot initialize MultiDomains from invalid String value icon"}`
(verified live 2026-09-13). The valid names are `icon_global`, `icon_seamless`,
`icon_eu`, `icon_d2`. zoom.earth's "icon" = **`icon_global`** (~11 km global run).
This is pinned by `test_wire_request_uses_icon_global` so it can't regress.

## Endpoint contract

```
GET /api/v1/humidity?lat=22.2&lon=69.4&span=3.0&hours=0
```

| param | range | default | meaning |
|-------|-------|---------|---------|
| `lat` | −90…90 | required | centre latitude |
| `lon` | −180…180 | required | centre longitude |
| `span` | 0 < s ≤ 30 | 3.0 | half-extent of the box in degrees (span 3 → 6°×6° view) |
| `hours` | 0…48 | 0 | forecast hour to display (0 = now) — drives the time slider |

Response (`200`):

```jsonc
{
  "centre": {"lat": 22.2, "lon": 69.4},
  "span_deg": 3.0, "grid_n": 9, "step_deg": 0.75,
  "hours_ahead": 0,
  "valid_time": "2026-09-13T07:00",          // ICON valid hour, UTC ISO
  "model": "icon_global (DWD ICON global) via Open-Meteo — the model zoom.earth's humidity map displays",
  "source": "https://open-meteo.com/ (DWD ICON, CC-BY-4.0)",
  "n_points": 81,
  "points": [                                 // row-major, north→south (like a raster)
    {"lat": 25.2, "lon": 66.4, "rh_pct": 58.0, "temp_c": 31.5,
     "dew_point_c": 22.4, "dew_depression_c": 9.1,
     "land": true, "color": "#F4D03F"}
    // … 81 points …
  ],
  "legend": [
    {"value": 0,  "color": "#B3541E", "label": "0% — desert-dry"},
    {"value": 20, "color": "#E67E22", "label": "20% — very dry"},
    {"value": 40, "color": "#F4D03F", "label": "40% — dry"},
    {"value": 60, "color": "#A9DF72", "label": "60% — moderate"},
    {"value": 75, "color": "#58D68D", "label": "75% — humid"},
    {"value": 85, "color": "#2E9E8F", "label": "85% — very humid"},
    {"value": 100, "color": "#1A5276", "label": "100% — saturated"}
  ],
  "summary": {"rh_min": 44.0, "rh_max": 91.0, "rh_mean": 68.4}
}
```

Errors are honest, never fabricated:
`{"error": "…", "centre": …, "span_deg": …, "hours_ahead": …, "hint": "retry later…"}` with HTTP 500 from the endpoint.

## How the grid is fetched (one API call, not 81)

`pipeline/humidity.py` follows the established cartesian-pair pattern
(`field_explorer.fetch_met_grid`, `openmeteo_sst.get_sst_grid`):

- `_grid_pairs(lat, lon, span, n)` → n×n **zip-paired** coordinate lists
  (row-major, north→south). One Open-Meteo call with
  `latitude=22.20,22.20,…&longitude=69.40,69.47,…` returns a **list of location
  objects zip-paired to the request order** — verified live. (A single-coordinate
  request can return a bare dict; the module normalises both.)
- `hourly=relative_humidity_2m,temperature_2m,dew_point_2m`,
  `forecast_hours = hours + 1`, `timezone=UTC`; values read at index `hours`.
- Default 9×9 = 81 points; internal max 16×16 = 256 points — still one call.
- Cached 30 min (`ttlcache`) keyed `humidity:{lat:.1f}:{lon:.1f}:{span:.1f}:{hours}:{n}`
  — a slider dragging across hours hits cache per hour-step, same pattern as `/field`.
- `land` flags from the GLOBE landmask (same as `/field`); `land=None` if the mask
  is unavailable — the frontend should then skip land-shading, not guess.

## Palette

`PALETTE` in `pipeline/humidity.py` — 7 stops, dry-orange → moist-teal/blue:

| RH % | hex | feel |
|------|-----|------|
| 0 | `#B3541E` | desert-dry |
| 20 | `#E67E22` | very dry |
| 40 | `#F4D03F` | dry |
| 60 | `#A9DF72` | moderate |
| 75 | `#58D68D` | humid |
| 85 | `#2E9E8F` | very humid |
| 100 | `#1A5276` | saturated |

`color_for_rh()` interpolates linearly in RGB between stops; unknown RH → `#808080`.
**Tuning:** the exact zoom.earth ramp is their choice; if you want a closer visual
match to your screenshots, edit `PALETTE` (value, hex) — `legend()` and
`color_for_rh()` derive from the same table, so one edit updates map + legend
together. Re-run `pytest pipeline/tests/test_humidity.py` after editing (the
endpoint tests read the palette dynamically).

## Frontend rendering recipe

1. **Grid → canvas**: the points are a regular raster (row-major, north→south).
   For each point fill a rect of size `step_deg` in map pixels, colour =
   `point.color` (server pre-computes it; or use `legend` to build your own ramp).
   Interpolate with browser canvas smoothing (`imageSmoothingEnabled=true`) for the
   zoom.earth "continuous field" look, or disable it for a blocky model-grid look.
2. **Overlay on the basemap**: draw the canvas as an Leaflet/MapLibre `L.imageOverlay`
   / raster source with opacity ~0.65 — same as the existing SST layer treatment.
   Sea points can be dimmed slightly if you only want the land RH (use `point.land`).
3. **Time slider (0–48 h)**: slider value = `hours`; on change call
   `GET /api/v1/humidity?...&hours=<h>`. Because responses are cached server-side
   per (centre, span, hour), stepping the slider is cheap after the first pull.
   Show `valid_time` from the response next to the slider so users see the actual
   ICON valid hour, not just "hour +3".
4. **Legend**: render `legend[]` as a gradient bar — the JSON is ready to draw.
5. **Dew-point bonus**: `dew_depression_c` (T − Td) is served per point; low values
   (< 2 °C) ≈ fog/condensation risk — useful for the fishermen's advisory UX.

## SIH-2026 porting notes (prabhbani/ORCA-SIH-2026)

- Copy `pipeline/humidity.py` verbatim (stdlib-only, no new deps) plus
  `pipeline/tests/test_humidity.py`.
- Wiring in their FastAPI (`routes_v1.py`): same shape as their other cached
  getters —
  ```python
  @router.get("/humidity")
  def humidity(lat: float, lon: float, span: float = 3.0, hours: int = 0):
      from pipeline.humidity import get_humidity_field
      return get_humidity_field(lat, lon, span, hours)
  ```
  (add their usual `Query(...)` bounds and deadline wrapper if present).
- Their `ttlcache` may live elsewhere — check the import path at the top of
  `humidity.py` and adjust, or pass `_fetcher` and cache at the route layer.
- Frontend: their map stack (Leaflet in the SIH repo) — see recipe above; the
  layer needs no API key so it works from any origin.

## Verification log

- 2026-09-13, live via API proxy, Kutch 22.2N/69.4E: `models=icon_global` +
  `forecast_hours=2` returned RH 63–65 %, T 31.3–31.9 °C, Td 23.6–23.9 °C,
  zip-paired location list — wire format confirmed; `models=icon` rejected
  (the reason this constant says `icon_global`).
- Offline suite: `pytest pipeline/tests/test_humidity.py` — 9 tests (geometry,
  hour selection, palette/legend, land flags, error paths, clamping, wire params).
- Full repo suite: 300 passing (humidity suite included; 7 pre-existing
  sandbox-network failures unrelated).
