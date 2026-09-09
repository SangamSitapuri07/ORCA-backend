# ORCA — Complete API Guide

> **SIH26176 (ISRO) · Marine EcOsystem Reasoning with Collaborative Agents**
> Ek hi sachchai: **har number ka source named hai, har failure ka reason
> honest hai, koi dummy/placeholder data kahin nahi.**

Yeh guide 3 cheezein batati hai:
1. **External APIs** — humne kahan se uthaya (real hosts, gov agencies), kis
   feature ke liye, unse kya data fetch hota hai, abhi status kya hai
2. **ORCA ke apne endpoints** (`/api/v1/*`) — kaun kya deta hai, params,
   response, kaun consume karta hai (app tab / web / judges)
3. **Data-flow + verdict rules + caching/honesty policy** — judge ke har
   "ye number aaya kahan se?" ka jawab

---

## 1. Architecture — flow of real data

```
        EXTERNAL SOURCES (12)                          CONSUMERS
 ┌───────────────────────────────┐
 │ Satellites  : MOSDAC OCM-3    │        ┌──────────────────────┐
 │               OC-CCI · NOAA   │        │ Flutter app (6 tabs) │
 │ Models      : Open-Meteo      │        │  · Home advisory     │
 │               (MeteoFrance /  │        │  · Map probe         │
 │               ECMWF IFS)      │  HTTP  │  · Navigate+verdict  │
 │ Activity    : Global Fishing  │ ─────► │  · AI 10 agents      │
 │               Watch (AIS)     │        │  · SOS context       │
 │ Advisories  : INCOIS PFZ/LAS  │        │ Next.js web dashboard│
 │ Storms      : JTWC (US Navy)  │        │ tools/ verify scripts│
 │ Terrain     : GLOBE 1km (off.)│        │ curl/judges          │
 └───────────────┬───────────────┘        └──────────────────────┘
                 ▼
     pipeline/*.py fetchers (timeouts + retries + honest failure notes)
                 ▼
   caches: SQLite blob (big NetCDF) + in-memory TTL (small JSON)
                 ▼
   engines: zone snapshot · 10-agent reasoner · advisory (WMO/IMD
           thresholds) · route-check (GLOBE 2-km sampling) ·
           transit verdict (30-km sampling × live forecast)
                 ▼
            backend/main.py (FastAPI) → /api/v1/*
```

---

## 2. External APIs — kahan se, kisliye, kya milta hai

> "Working?" ka jawab **runtime `/api/v1/health` se live milta hai** — neeche
> table me wahi status likha hai jo health ne last verify kiya.

| # | Source (agency) | Host (real) | Auth | Kya fetch hota hai | ORCA me use | Status* |
|---|---|---|---|---|---|---|
| 1 | **Open-Meteo Marine** (MeteoFrance MFWAM / ECMWF WAM wave models) | `marine-api.open-meteo.com` | none | hourly: wave height, swell, **SST**, ocean **current speed+direction** — 96 h horizon | every advisory, safe window, transit verdict, map probe, 48-h chart | ✅ live |
| 2 | **Open-Meteo Forecast** (ECMWF IFS) | `api.open-meteo.com` | none | hourly wind, gusts (48-h gale check via WMO 34 kn), rain | advisory rules, verdict, chart | ✅ live |
| 3 | **Open-Meteo Daily** | `api.open-meteo.com` | none | daily sky condition (WMO codes) | verdict context | ✅ live |
| 4 | **Open-Meteo Archive** | `archive-api.open-meteo.com` | none | past-year hourly (2024/2025) — **anomaly baseline** | Anomaly agent ("aaj vs normal") | ⚠️ engine ready; host flaky from some networks — failure shown honestly |
| 5 | **NOAA CoastWatch ERDDAP** (US NOAA NESDIS) | `coastwatch.noaa.gov` | none | satellite **chlorophyll-a** (mg/m³); retry chain today → **3-day lag → 7-day lag**; DINEOF gap-filled product walks back 14 days | fish-food map, hotspots, field layer | ✅ live |
| 6 | **ESA OC-CCI v6** (European Space Agency ocean colour — via NOAA's ERDDAP mirror) | `comet.nefsc.noaa.gov` | none | chlorophyll (independent cross-check of #5) | chlorophyll cross-validation | ✅ live — but **monsoon clouds physically block optical sensing**; we SAY "cloud-masked" instead of faking |
| 7 | **ISRO MOSDAC** (India's own — Oceansat-3 **OCM-3**) | `mosdac.gov.in` | username+password (`.env`, never committed) | OCM-3 chlorophyll granules (NetCDF/HDF5) — real SSO login → search → download with a **24 s honest wall cap** so a slow GOI link never hangs the skipper | India-primary chlorophyll | ✅ live (link slow at times — background retry, 10-min cool-down, reason named) |
| 8 | **INCOIS ERDDAP** (Indian Nat'l Centre for Ocean Info Services) | `erddap.incois.gov.in` | none | Indian-region chlorophyll/ocean products | region fallback | ✅ live |
| 9 | **INCOIS LAS** (Live Access Server) | `las.incois.gov.in` | none | SST / ocean params (SIGALRM-capped, 12–30 s) | fallback only | ⚠️ "server unreliable" (their side) — honestly labelled; never blocks a verdict |
| 10 | **INCOIS PFZ — official daily govt advisory lines** | `incois.gov.in` (GeoServer WFS `PFZ_Automation:pfzlines`) | none | today's **Potential Fishing Zone** line geometry | map/PFZ features + upcoming tap-sheet zones | ✅ live |
| 11 | **Global Fishing Watch** (AIS-derived) | `gateway.api.globalfishingwatch.org` | API token (`.env`) | fishing **effort** (hours/km²) + **fleet/vessel** lists per region; **429 → 15 s backoff, retry once** | fleet-presence context, agents | ✅ live |
| 12 | **JTWC** (US Navy Joint Typhoon Warning Center) | `www.metoc.navy.mil` | none | active tropical **cyclone warnings** (text, parsed) | alerts feed, risk agent | ✅ live |
| 13 | **GLOBE 1 km land mask** (offline raster) | bundled data (no network) | none | land/water classification, 1 km resolution | **course verification every 2 km**, detour computation, land-masking chlorophyll pixels (stops on-land "hotspots") | ✅ 100 % offline — demo works with internet OFF |
| 14 | **Nominatim** (OpenStreetMap) — app-side | `nominatim.openstreetmap.org` | none (polite UA) | harbour/beach/village search | app map search | ✅ live |

\* Status ko fresh verify karna ho to: `curl localhost:8000/api/v1/health`

### Honesty in action (last verified on phone, Mumbai/Veraval points)
- *"OC-CCI: all pixels within ±0.75° are cloud-masked today (monsoon cover —
  satellites can't see through clouds). NOAA primary is used."*
- *"NOAA ERDDAP (today, 3-day & 7-day lag tried): all ERDDAP datasets failed"*
- *"MOSDAC OCM-3: download too slow (> 24 s wall cap) — background retry in
  ~10 min"* ← ye cap/feature hai, crash nahi
- Validation agent card shows e.g. **"3/7 sources OK"** — weak coverage bhi
  dikh bigay, chhipaya nahi.

---

## 3. ORCA's own API — `GET /api/v1/*` (FastAPI)

Base URL locally: `http://<laptop-IP>:8000` (app ke Info tab me set hota hai).
Convention: sab responses **sources_used / sources_failed** ke saath —
evidence-first.

| Endpoint | Kya karta hai | Key params → return | Kaun use karta hai |
|---|---|---|---|
| `GET /api/v1/health` | source-by-source live status, credentials presence, cache stats | — → `{status, version, build_commit, data_sources{…}, cache{…}}` | app Info tab "Check" button, demo pre-flight |
| `GET /api/v1/zone` | ek spot ka full snapshot (waves, SST, CHL, current, GFW…) | `lat, lon` → zone object | map probe, agents |
| `GET /api/v1/grid` | area grid snapshot (map painting) | `lat, lon, span` → points[] | web map, field tiles |
| `GET /api/v1/reason` | **10 collaborative agents** same data pe (risk/ecology/anomaly/validation …) | `lat, lon, date?, include_gfw?, agents?` → `{agents:[{agent, summary, verdict}], overall_risk, data_coverage{known,total,sources_failed}, …}` | app **AI tab** |
| `GET /api/v1/advisory` | skipper verdict — WMO/IMD small-craft thresholds, bilingual plain lines, safe window, variables, hourly chart | `lat, lon` → `{verdict, color, headline, headline_hi, plain_en[], plain_hi[], variables{…}, safe_window, hourly_chart, sources…}` | app **Home**, Navigate destination card |
| `GET /api/v1/field` | field explorer (chlorophyll + met grid, land-masked) | `lat, lon` | app Map probe deep-dive |
| `GET /api/v1/route-check` | course verifier: rhumb line **har 2 km** GLOBE mask; land lage → **1 REAL computed detour waypoint** (16 angles × 5 radii, sab re-validated); kuch na mile → honestly `ok:false` | `from_lat, from_lon, to_lat, to_lon` → `{ok, detour, legs[[lat,lon]…], land_hit?, reason, distance_km/nm, bearing_deg}` | app **Navigate** polyline + verified badge |
| `GET /api/v1/route-advisory` | **TRANSIT VERDICT** — "yahan se wahan safe?" PUREE route ka: legs har ~30 km sample (≤5 pts, detour waypoint hamesha kept) × **5 parallel live forecasts** → per-point `good/caution/danger/unknown` (advisory ke SAME thresholds) → worst-case fold `go/caution/nogo/unknown` + start-point **safest departure window** | same params → `{verdict{level, points_known/total, land_verified}, points[{sail_km, wave_m, wind_kn, state, why/note}], safe_window_at_start, sources…}` | app **Navigate** verdict card |
| `GET /api/v1/tiles/{z}/{x}/{y}.png` | server-rendered **PNG data tiles** (real data → real pixels) | xyz slippy coords | web map layer |
| `GET /api/v1/layers` | available data layers metadata | — | web |
| `GET /api/v1/alerts` | active alert cards (JTWC cyclones + rule flags) | — | app/web alerts hook |
| `GET /api/v1/alerts/simulate` | **clearly-labelled demo injector** (never mixed with real feed) | — | demo script only |
| `GET /api/v1/agents` | 10-agent registry (id, role, sources, implemented) | — | app AI tab header, judges |
| `GET /api/v1/datasets` · `/zones` | dataset/zone catalogs + provenance | — | web, field explorer |
| `POST /api/v1/chat` + `WS /ws/chat` | optional LLM chat on top of live data (Ollama) | currently **paused by design choice** — returns honest unavailable | future |
| `POST /api/v1/feedback` | skipper feedback capture | `{…}` → stored | app |

*(Kuch legacy aliases bhi mount hain for backwards compatibility; canonical
paths = `/api/v1/*`.)*

---

## 4. Decision rules (exact — koi hidden weight nahi)

Verdict **worst-case fold** hai (average danger chhupa nahi sakta):

| Signal | 🟢 good | 🟠 caution | 🔴 danger |
|---|---|---|---|
| wave (now ya 48-h max) | < 2.5 m | ≥ **2.5 m** | ≥ **4.0 m** |
| gusts (48-h max) | < 34 kn | — | ≥ **34 kn** (WMO gale) |
| sustained wind (48-h max) | < 20 kn | ≥ **20 kn** (Beaufort 5) | — |
| surface current | ≤ 3 kn | > 3 kn → honest **note** (not a state) | — |

Land: GLOBE 2-km sampling — `blocked` ⇒ NO-GO regardless of weather;
`detour` ⇒ real waypoint listed; mask missing ⇒ `unverified` (kabhi "safe"
nahi bolte).

---

## 5. Caching / politeness policy (servers pe bojh nahi)

| Kya | TTL / cap | Kyun |
|---|---|---|
| point forecast cache (0.25° cell) | 30 min | Open-Meteo hammering zero |
| route-advisory | 30 min TTL | 5-point analysis reuse |
| MOSDAC download | **24 s wall cap**, 10-min cool-down | GOI link slow — app kabhi latkti nahi |
| GFW 429 burst | 15 s wait, **retry exactly once** | token quota respect |
| chlorophyll lags | today → 3d → 7d (DINEOF ≤ 14 d) | satellite reality ke saath honest |

## 6. Cross-check khud karo (judge script)

```powershell
curl "http://localhost:8000/api/v1/health"
curl "http://localhost:8000/api/v1/route-advisory?from_lat=19.0&from_lon=72.8&to_lat=18.6&to_lon=71.2"
curl "http://localhost:8000/api/v1/advisory?lat=20.9&lon=70.37"
```

Expected (real run, 2026-09-09): transit 174 km, 5/5 points live, wave
1.02 m → 1.48 m offshore badhti hui — fetch-length physics ke saath match.

---

*Docs for judges & team · maintained with the code · sister repo:
[SangamSitapuri07/SIH](https://github.com/SangamSitapuri07/SIH) (frontends).*
