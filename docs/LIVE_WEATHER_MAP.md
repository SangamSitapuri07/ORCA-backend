# Live Animated Weather Map (zoom.earth-style) — ORCA-backend

**Open it:** start the backend and visit **`/map`** — an interactive map
with a **zoom.earth-style layer picker**: nine selectable layers
(humidity · temperature · wind speed · gusts · rain · clouds · sea temp ·
waves · currents), each repainting the animated colour wash with its own
palette and legend. Wind particles, satellite-current particles and wave
chevrons animate on top; time slider, hover readout and layer toggles
included. Weather from the same model family zoom.earth uses (DWD ICON
via Open-Meteo); sea layers from NOAA satellites — all first-party.

```
GET /map                          → the map page (no build step, Leaflet from CDN)
GET /api/v1/weather/grid?...      → wind + humidity + temp feed
GET /api/v1/ocean/grid?...        → currents + waves + SST feed
GET /api/v1/weather/grid?demo=1   → bundled REAL ICON snapshot (offline fallback)
GET /api/v1/ocean/grid?demo=1     → bundled REAL ocean snapshots
```

## Architecture

```
browser (/map)
 ├─ Leaflet + real basemaps fetched DIRECTLY by the browser:
 │   Esri World Imagery (satellite, default), CARTO Dark, OSM Streets —
 │   switcher in the controls; auto-fallback chain per provider ends at
 │   the first-party proxy /api/v1/tiles/{z}/{x}/{y}.png
 ├─ #field canvas     humidity colours: per-frame 9×9 (or 12×12) rasters
 │                    cross-faded between hourly frames, HALF-CELL-CORRECT
 │                    stretch (grid point i lands at i·cell px — the same
 │                    fix proven in scripts/render_humidity_preview.py)
 ├─ #wavemark canvas  wave chevrons at grid points — point TOWARD travel,
 │                    coloured by significant wave height (calm→rough)
 ├─ #currents canvas  cyan particles advected through the satellite
 │                    geostrophic current field (displayed 8× true speed,
 │                    like every current visualiser), over water only —
 │                    null cells ARE the coastline
 ├─ #particles canvas ~1–2k particles advected through the time-interpolated
 │                    10 m wind field; mercator-correct speeds; fading
 │                    trails (destination-out); positions in WORLD px so
 │                    they stay geo-glued while panning
 └─ HUD               bilinear sampling of u/v/rh/temp at the cursor;
                     wind direction = (270 − atan2(v,u)) % 360 — ORCA's
                     corrected compass convention
backend
 └─ GET /api/v1/weather/grid — ONE Open-Meteo call for the whole grid ×
    all frames (zip-paired coordinate lists, models=icon_global,
    wind_speed_unit=ms), cached 30 min per centre+span+frames+grid
```

## Endpoint contract

```
GET /api/v1/weather/grid?lat=22.2&lon=69.4&span=3.0&frames=8&grid=12
```

| param | range | default | meaning |
|-------|-------|---------|---------|
| `lat`, `lon` | ±90 / ±180 | required (live) | centre of the box |
| `span` | 0 < s ≤ 30 | 3.0 | **full width** of the box (3 → 3°×3°) |
| `frames` | 2…25 | 8 | hourly frames returned (8 = now…+7 h) |
| `grid` | 3…16 | 9 | grid is grid×grid points |
| `demo` | — | false | `1` → serve the bundled snapshot (ignores lat/lon) |

Response (compact — built for animation, one value per point per frame):

```jsonc
{
  "demo": false, "fetched_at": "2026-09-13T07:41:00+00:00",
  "model": "icon_global (DWD ICON global) via Open-Meteo — …",
  "center": {"lat": 22.2, "lon": 69.4},
  "span_deg": 3.0, "grid_n": 9, "step_deg": 0.375,
  "times": ["2026-09-13T07:00", … ],        // UTC, hourly
  "lats": [23.7, … 20.7],                   // 9 row lats, DESCENDING (N→S)
  "lons": [67.9, … 70.9],                   // 9 col lons, ascending
  "u":   [[…81 m/s], … per frame],          // eastward component (derived)
  "v":   [[…], …],                          // northward component (derived)
  "rh":  [[…], …], "temp": [[…], …],
  "legend": [{value, color, label}, …]      // same palette as /api/v1/humidity
}
```

Points are **row-major north→south**: point index `p = row*grid_n + col`.
Missing values are `null` — never fabricated. Errors are honest HTTP 500s.

## Ocean layers — GET /api/v1/ocean/grid

The weather feed carries **7 hourly fields** per point — `u`,`v` (derived
from speed+direction), `rh`, `temp`, **`pr`** (precipitation mm),
**`gust`** (km/h), **`cloud`** (%) — one Open-Meteo call, same lattice.

Same lattice/params as the weather grid (`lat, lon, span ≤30, frames ≤25,
grid ≤16`, `?demo=1`). Three independent real sources, no logins:

| layer | source (verified live 2026-09-13) | cadence |
|---|---|---|
| currents `cu`,`cv` | NOAA CoastWatch **satellite altimetry geostrophic currents** (`noaacwBLENDEDNRTcurrentsDaily`, 0.25°; Sentinel-3A/B, CryoSat2, Jason-2/3, **SARAL/AltiKa — ISRO**) | daily, ~3-day NRT lag |
| `sst` | NOAA Coral Reef Watch **CoralTemp** satellite SST (`noaacrwsstDaily`, 0.05° native, sampled 0.25°) | daily, ~2-day lag |
| waves `wh`,`wd`,`wp` | **Open-Meteo Marine** (height m, FROM-direction °, period s) | hourly |

- Native satellite cells are bilinearly interpolated server-side onto the
  weather lattice; coastal cells with null corners take the nearest valid
  corner (never an invented gradient); deep-land stays `null`.
- Currents/SST are daily (single frame, constant across the time slider);
  waves are hourly and follow the same clock (nearest-hour mapping).
- Each source fails independently — an outage drops that layer with an
  honest `errors` entry, the rest still render.

**Demo snapshot** (`pipeline/ocean_demo_snapshot.py`): real relayed values —
currents 2026-09-10 00Z, SST 2026-09-11 12Z, waves 2026-09-13 08Z —
verbatim, with the genuine Gulf-of-Kutch **0.76 m/s jet** in the altimetry.
54 of 81 demo lattice points are sea; the 27 land nulls trace the actual
Kutch coastline. The weather demo (`pipeline/weather_demo_snapshot.py`)
carries all **7 variables** — wind/RH/temp from the original 07:00 fetch,
precipitation/gusts/clouds relayed the same day with
`start_hour`/`end_hour` so the frames align — including a real convective
rain cell: **2.1–2.8 mm/h** over Saurashtra 10:00–12:00 UTC, gusts to
**51 km/h**.

## Layer picker (zoom.earth-style)

Left rail on `/map`; each selection swaps the wash, palette and legend:

| layer | source | palette | notes |
|---|---|---|---|
| humidity % | ICON `rh` | existing RH ramp | default |
| temperature | ICON `temp` | 20–36 °C blue→red | |
| wind speed | ‖u,v‖·3.6 | 0–75 km/h blue→red | particles stay |
| wind gusts | ICON `wind_gusts_10m` | 10–90 km/h | gusts ≥ wind, always |
| rain | ICON `precipitation` | 0.05–12 mm/h green→purple | **dry (<0.05) = transparent** |
| clouds | ICON `cloud_cover` | 20–100 % grey→white | <10 % transparent |
| sea temp | CoralTemp `sst` | 25–29 °C | sea cells only |
| waves | Marine `wh` (nearest hour) | 0–4 m | chevrons stay |
| currents | ‖cu,cv‖ | 0–1.2 m/s | cyan particles stay |

Rain/cloud "transparent below cut" mirrors zoom.earth: a dry sky paints
nothing — the map tells you it's dry by NOT lying with colour.

## Wire-format facts (verified live 2026-09-13)

- `models=icon_global` — bare `icon` is rejected ("Cannot initialize
  MultiDomains").
- **u/v components are NOT variables** on this endpoint
  (`u_wind_component_10m` → HTTP 400). We request
  `wind_speed_10m,wind_direction_10m` with `wind_speed_unit=ms` and derive
  `u = −s·sin θ`, `v = −s·cos θ`. Round-trips exactly to the reported
  FROM-direction — pinned by `test_uv_from_speed_and_direction`.
- Multi-coordinate responses come back as a **zip-paired list** of
  location objects (single-coordinate can return a bare dict; normalised).

## Demo mode — honest, never fabricated

`pipeline/weather_demo_snapshot.py` embeds a **real** DWD ICON run
(2026-09-13 07:00–14:00 UTC, Kutch 9×9, wind+RH+temp) fetched and relayed
verbatim (the build sandbox has no direct egress to open-meteo.com; the
payload was pulled row-by-row so no proxy chunk ever split a value). The
page tries the live endpoint first; if it fails it falls back to
`?demo=1` and clearly badges itself **“DEMO — REAL ICON SNAPSHOT”** in
amber. Integrity is enforced by tests: shapes, ranges, and a **567-value
cross-check** against an independent earlier transcription of the same
model run (shifted one hour) — zero mismatches.

## What you should see (Kutch demo)

- **Colours:** dry orange-yellow over the Rann interior (RH ~42–52 %),
  moist teal-blue over the Arabian Sea (~83–87 %) and Saurashtra coast —
  animating through 8 hours as the slider plays (RH range drifts
  48–89 % → 71–97 %: the interior moistens in the evening).
- **Wind:** monsoon westerlies flowing east over the sea (25–35 km/h,
  from ~270°), near-calm swirls over the Rann — particles move at a
  time-accelerated rate (~5 simulated hours per real second, like
  earth.nullschool.net).
- **Currents (cyan):** slow satellite-measured flows — strongest in the
  Gulf of Kutch channel (~0.7–0.8 m/s), drawn 8× true speed so they're
  visible next to wind.
- **Waves (chevrons):** ~1.6–1.8 m swell from the SSW offshore, decaying
  to 0.3–0.5 m inside the Gulf; arrows point where waves travel.
- **Sea temp (rail):** ~27.9–28.8 °C water painted over the satellite
  basemap; the rail switches the colour wash and legend.
- **Rain (rail):** mostly transparent (dry September sky over Kutch) with
  a real convective cell lighting up Saurashtra green→orange→red at
  10:00–12:00 — scrub the time slider to watch it develop.
- **Gusts (rail):** same hue family as wind but shifted hotter — gusts
  are always ≥ sustained wind, and the wash shows it.
- **Hover:** RH, wind speed/dir (m/s, km/h, compass), temperature at the
  cursor, at the displayed (interpolated) time.

## Production behaviour vs preview sandbox

- **Production (backend with internet):** badge shows LIVE; the grid
  follows the viewport (re-fetched, debounced, on pan/zoom); OSM tiles
  render under the field.
- **This build sandbox:** the sandbox has no server-side egress to
  open-meteo.com → the live attempt fails in <50 ms (honest 500) and the
  page falls back to the demo snapshot. Basemaps are unaffected: they are
  fetched client-side by YOUR browser from Esri/CARTO/OSM, so the preview
  shows real satellite imagery under the animated field (the humidity
  wash is drawn at 84% opacity so the geography shows through — flip to
  Dark for the nullschool look). If a provider is unreachable from the
  viewer's network the layer auto-falls-forward, ending at the backend
  proxy. Proper attribution (Esri/Maxar, CARTO, OSM) is shown bottom-right.

## SIH-2026 porting (prabhbani/ORCA-SIH-2026)

Copy verbatim (no new backend deps; stdlib only):
`pipeline/weather_grid.py`, `pipeline/weather_demo_snapshot.py`,
`frontend/weather_map.html`, `frontend/weather_map.js`, and the two tests.
Wire in their `routes_v1.py`:

```python
@router.get("/weather/grid")
def weather_grid(lat: float, lon: float, span: float = 3.0,
                 frames: int = 8, grid: int = 9, demo: bool = False):
    from pipeline.weather_demo_snapshot import demo_payload
    from pipeline.weather_grid import get_weather_grid
    if demo:
        return demo_payload()
    return get_weather_grid(lat, lon, span, frames, grid)
```

Serve `frontend/` statically (or inline it) at `/map`. Their Leaflet map
can reuse the two canvases as an overlay pane for the existing views.
Palette lives in ONE place per side — `pipeline/humidity.py:PALETTE` and
its JS mirror at the top of `weather_map.js` — keep them in sync (the
endpoint also ships `legend`, so the frontend can build from data).

## Files

| path | what |
|------|------|
| `frontend/weather_map.html` | page shell, dark UI, controls, legend |
| `frontend/weather_map.js` | canvases, particle engines, time engine, HUD |
| `pipeline/weather_grid.py` | live multi-frame weather grid (one API call) |
| `pipeline/weather_demo_snapshot.py` | real ICON snapshot + integrity story |
| `pipeline/ocean_grid.py` | currents + waves + SST (two ERDDAP + one marine call) |
| `pipeline/ocean_demo_snapshot.py` | real satellite/marine snapshots, verbatim |
| `pipeline/tests/test_weather_grid.py` | 11 offline tests (weather) |
| `pipeline/tests/test_ocean_grid.py` | 9 offline tests (ocean, incl. coastal-null rules) |

**Attribution:** weather — DWD ICON via Open-Meteo (CC-BY-4.0); currents —
NOAA NESDIS CoastWatch blended altimetry; SST — NOAA Coral Reef Watch
CoralTemp; waves — Open-Meteo Marine; basemaps — Esri/Maxar, CARTO, OSM.
