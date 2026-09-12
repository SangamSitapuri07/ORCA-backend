# ORCA — Complete API and Integration Guide

> **SIH26176 (ISRO) · Marine Ecosystem Reasoning with Collaborative Agents**
>
> **Audit conclusion (2026-09-12): all integrations are not currently
> working.** A real hostname, a written adapter, a mocked unit test, cached
> output, or a 200 response from `/health` is not evidence that a provider
> returned live data.

This guide separates four questions that must not be conflated:

1. **Real service:** does the named host/product exist?
2. **Wired:** does production backend code actually call it?
3. **Configured here:** are required credentials/dependencies present in this checkout/runtime?
4. **Live-successful here:** did a forced request return usable provider data during this audit?

## 1. Phase-1 data flow actually present

```text
Flutter Android client / Next.js web client
              │
              │ HTTP, SSE, WebSocket (no direct scientific-provider calls)
              ▼
backend/main.py — the single authoritative FastAPI backend
              │
              ├─ deterministic advisory / route / alert / GIS rules
              ├─ eleven-stage analytical trace
              ├─ optional local Ollama explanation (not safety computation)
              └─ pipeline provider adapters
                    ├─ Open-Meteo Marine / Forecast / Archive
                    ├─ NOAA CoastWatch ERDDAP / ESA OC-CCI
                    ├─ INCOIS LAS / official PFZ WFS
                    ├─ optional MOSDAC / optional GFW
                    ├─ supplemental JTWC guidance
                    ├─ MarineRegions, OSM and optional OpenSeaMap display layers
                    └─ local GLOBE 1 km land mask
```

What is **not** present in this checkout:

- PostgreSQL/PostGIS and authoritative EEZ/MPA/restricted-zone GIS storage;
- RAG retrieval (the agent registry reports it unavailable);
- Supabase routes/storage (core safety remains independent of Supabase);
- a running Ollama server/model in the audited runtime;
- active SQLite/blob caching. Active caches are in-memory TTL caches, an OSM
  tile disk cache, and provider-specific downloaded-file handling.

## 2. External service audit

**Live test location:** offshore Gujarat control point `20.90 N, 69.80 E`.
**Test date:** 2026-09-12. “Failed here” describes this runtime, not a claim
that the public provider is globally down.

| Source / host | Real service? | Production adapter wired? | Configured in this checkout? | Forced live result here | Honest backend behaviour |
|---|---:|---:|---:|---|---|
| **Open-Meteo Marine** — `marine-api.open-meteo.com` | Yes | Yes — `forecast.py`, `openmeteo_sst.py`, field/route/advisory paths | Yes; no key required | **No usable data:** TLS connection closed with EOF | Scientific values stay absent; advisory/route become `unknown`; failure is listed |
| **Open-Meteo Forecast** — `api.open-meteo.com` | Yes | Yes — wind, gust, rain, weather-code, alert paths | Yes; no key required | **No usable data:** TLS EOF | No calm/all-clear is inferred from missing wind/gust/weather evidence |
| **Open-Meteo Daily** — `api.open-meteo.com` | Yes | Yes — daily weather agent/advisory context | Yes; no key required | **No usable data:** TLS EOF | Daily weather remains unavailable and blocks a `go` verdict |
| **Open-Meteo Archive** — `archive-api.open-meteo.com` | Yes | Yes — bounded anomaly baseline | Yes; no key required | **No usable data:** remote access failed in the forced audit | Anomaly status is `unknown`; no baseline is fabricated |
| **NOAA CoastWatch ERDDAP** — `coastwatch.noaa.gov` | Yes; configured dataset IDs are real | Yes — chlorophyll point/grid and fallback chain | Yes; no key required | **No usable data:** all configured datasets ended in TLS EOF | Returns exact attempted-dataset failure; no chlorophyll value is invented |
| **ESA OC-CCI v6** via `comet.nefsc.noaa.gov` | Yes | Yes — optional independent chlorophyll comparison | Yes; no key required | **No usable data:** TLS EOF | Cross-check is marked unavailable; code does not assume the cause was cloud, and a numeric value without an observation time is rejected |
| **ISRO MOSDAC OCM-3 L2C LAC** — `mosdac.gov.in` / `www.mosdac.gov.in` | Yes | Yes — optional login/search/download/extract cross-check | **No:** `MOSDAC_USERNAME` and `MOSDAC_PASSWORD` are absent | Not authenticated/tested | Adapter remains disabled and says credentials are required; it is not called “live” or the primary source |
| **INCOIS ERDDAP** — `erddap.incois.gov.in` | Yes | **No selected data adapter:** URL is catalogued, current code does not query it | N/A | Not tested through ORCA | `/health` reports `not_integrated`; it is not described as a fallback |
| **INCOIS LAS OPeNDAP** — `las.incois.gov.in` | Yes | Yes — conditional backup chlorophyll path | Yes; no key required | **No usable data:** NetCDF I/O failure | Failure is listed; NOAA/OC-CCI remain separate attempts. A value is accepted only when its decoded time coordinate is within seven days of the requested date; the actual selected date is returned, and undated/stale-cache values are rejected |
| **INCOIS official PFZ WFS** — `incois.gov.in`, layer `PFZ_Automation:pfzlines` | Yes; official host/product | Yes — layer, nearest-PFZ, voyage candidate paths | Yes; no key required | **No usable geometry:** TLS EOF | `/voyage` returned `found:false`; `/layers` reported the PFZ error; no candidate point was invented |
| **Global Fishing Watch v3** — `gateway.api.globalfishingwatch.org` | Yes; v3 docs and nested report shape verified | Yes — effort and vessel/fleet context | **No:** `GFW_API_TOKEN`/`GFW_TOKEN` absent | Not authenticated/tested | Calls return “token not set”; no cached value masks auth/quota errors; parser supports nested `hours` and singular `vesselId` |
| **Ollama local HTTP API** — default `127.0.0.1:11434`, model `qwen3:8b` | Yes; locally deployed service | Yes — optional evidence-grounded explanation only | Host/model defaults exist, but no server/model is running here | Active health probe returned connection refused and `available:false` | Deterministic agents, advisory, and chat routing continue without LLM enrichment; safety logic never moves into Ollama |
| **JTWC** — `www.metoc.navy.mil` | Yes | Yes — cyclone parser, alerts, advisory, layer | Yes; no key required | **No usable bulletin:** TLS EOF | Returns an error and does not claim a successful “no cyclone” check. JTWC is supplemental U.S. DoD guidance; IMD/RSMC New Delhi is the official Indian authority |
| **GLOBE 1 km land mask** — local `global-land-mask` data | Yes | Yes — route/GIS/field land checks | **Yes** | **Passed locally:** `20.90,70.37` classified land; `20.90,69.80` water | Returns `None`/unverified if the mask is unavailable; no bounding box is used as an EEZ |
| **OpenStreetMap tile service** — `tile.openstreetmap.org` | Yes | Yes — first-party tile proxy with bounded cache | Yes; no key required | **Failed here:** ORCA returned HTTP 502 because no tile/cached fallback was available | 502 is explicit; an existing stale tile may be served with `no-cache`, never relabelled fresh |
| **OpenSeaMap seamarks** — `tiles.openseamap.org` | Yes | Yes — optional web overlay now uses a first-party bounded-cache proxy | Yes; no key required | **Failed here:** direct TLS failed and ORCA returned HTTP 502 with no cached fallback | Failure is explicit at the proxy; this overlay is not an official nautical chart and is off by default |
| **Nominatim** — `nominatim.openstreetmap.org` | Yes | **No** production search datasource is wired | N/A | Not tested through ORCA | `/health` reports `not_integrated`; the client catalog must not imply search works |
| **MarineRegions WFS** — `geo.vliz.be` | Yes | Yes — optional EEZ **display** feature in `/layers` | Yes; no key required | **No usable feature** in the endpoint audit | `/layers` reports `MarineRegions EEZ: upstream feature unavailable`; the GIS/safety agent does not use this optional layer for legal claims |

### Important interpretation

- `/api/v1/health` is deliberately **non-probing**. `wired`, `not_probed`,
  `configured`, and `available` for a local component do not mean the remote
  host answered now.
- HTTPS failures in this runner consistently ended with TLS EOF. That is
  evidence of failure from this environment, not proof that every provider was
  down worldwide.
- GFW and MOSDAC are blocked by missing credentials, independently of the
  runner's network problem.
- INCOIS ERDDAP and Nominatim were documentation/catalog entries, not live
  integrations; they are now labelled `not_integrated`.

### Configure the two authenticated providers

Keep credentials only in the backend runtime environment. Do not put them in
Flutter, commit them, paste them into an issue, or add real values to
`.env.example`.

```bash
cp .env.example .env
# Edit .env locally:
# GFW_API_TOKEN=<Global Fishing Watch access token>
# MOSDAC_USERNAME=<MOSDAC account>
# MOSDAC_PASSWORD=<MOSDAC password>

python tools/verify_credentials.py
# Restart FastAPI after changing the environment.
```

The verifier hides the token/password, uses a moving GFW date window, sums
fishing hours from nested response entries (top-level `total` is only a result
group count), and separately checks MOSDAC login. `/api/v1/health` will report
that credentials are configured, but provider liveness is established only by
the authenticated checks/on-demand calls.

## 3. ORCA endpoint audit

The backend was restarted from the edited checkout before the final contract
run. The production-mode core run exercised **24 HTTP calls**: 19 returned
intended 2xx responses, two validation/size-guard calls returned the intended
400, the disabled drill-alert route returned the intended 403, and the
OSM/OpenSeaMap tile proxies returned the intended explicit 502 upstream
failures. The
separate two-boat rescue drill exercised another **16 HTTP calls**, all of
which returned 200. A 2xx scientific response only proves the ORCA contract
worked; it may correctly contain no observations plus explicit source
failures.

### Core and scientific endpoints

| Endpoint | Parameters/body | Backend status | 2026-09-12 result |
|---|---|---|---|
| `GET /` | — | Wired | 200; service metadata returned |
| `GET /api/v1/health` | — | Wired, non-probing | 200; correctly showed GFW/MOSDAC unconfigured and Ollama/RAG/PostGIS/Supabase unavailable/not probed as applicable |
| `GET /api/v1/ollama/health` | — | Active probe | 200 contract; `available:false`, `status:unavailable` |
| `GET /api/v1/agents` | — | Wired | 200; eleven stages; RAG explicitly unavailable |
| `GET /api/v1/datasets` | — | Wired metadata | 200; catalog only, not provider liveness evidence |
| `GET /api/v1/zones` | — | Wired static starting coordinates | 200; eight coordinates, not observations |
| `GET /api/v1/zone` | `lat`, `lon`, optional `date`, `radius_deg`, `include_gfw` | Wired to provider adapters | 200 degraded in the audited run; no fabricated remote values. Current responses also retain per-value source/time/range in `observation_metadata`; the Flutter map exposes it under “Observation details” |
| `GET /api/v1/grid` | `min_lat`, `max_lat`, `min_lon`, `max_lon`, optional `step_deg`, `date`, `include_gfw` | Wired; GFW size guard | 200 degraded; one requested cell, no fabricated values, per-cell failures retained |
| `GET /api/v1/reason` | `lat`, `lon`, optional `date`, `include_gfw`, `agents` | Wired eleven-stage trace | 200; eleven stages, analytical risk `unknown`, no synthetic PFZ score. `data_coverage.scope=analytical_agents`; `known_stages/total_stages` are stage statuses, not verified provider counts. This endpoint never emits a skipper `go`; `/advisory` owns that decision |
| `GET /api/v1/advisory` | `lat`, `lon`, optional `date`, `include_gfw` | Authoritative deterministic skipper verdict | 200; `verdict:unknown`, no sources used, seven failures. Missing wave/wind/gust/daily-weather/cyclone evidence cannot become `go`; available `variable_details` retain source plus observation instant/window and retrieval time |
| `GET /api/v1/field` | `lat`, `lon` | Wired sampled NOAA/Open-Meteo view | 200 degraded; zero chlorophyll/met samples and explicit errors. Legacy `hotspots` means highest chlorophyll cells only—not PFZ, HAB, fish/catch, or advice |
| `GET /api/v1/route-check` | `from_lat`, `from_lon`, `to_lat`, `to_lon` | Wired local GLOBE check | 200; tested sea control returned `ok:true`, `detour:false` |
| `GET /api/v1/route-advisory` | same four coordinates | Wired GLOBE + per-point forecast fold | 200 degraded; 0/3 known points and corrected `verdict.level:unknown` (not caution/go) |
| `GET /api/v1/voyage` | `lat`, `lon`, optional `max_km` | Wired to official PFZ geometry only | 200 degraded; `found:false`, zero recommendations, PFZ failure named. If data exists, `score` is labelled experimental ordering—not INCOIS score, catch probability, or safety certificate |
| `GET /api/v1/layers` | optional `bbox`, `types=official_pfz,cyclone,port,eez` | Wired | 200; only three static port features in the tested `68.5,19.5,73.5,22.5` bbox; port citations labelled pending; PFZ/JTWC/MarineRegions failures listed and failed JTWC was not claimed as used |
| `GET /api/v1/tiles/{z}/{x}/{y}.png` | XYZ tile coordinates | Wired OSM base-map proxy | HTTP 502; honest upstream failure, not a fake image |
| `GET /api/v1/seamarks/{z}/{x}/{y}.png` | XYZ tile coordinates | Wired optional OpenSeaMap overlay proxy | HTTP 502; honest upstream failure, not a fake nautical overlay. The overlay is not an official chart |

### Alerts, chat, feedback, and streams

| Endpoint | Contract | 2026-09-12 result |
|---|---|---|
| `GET /api/v1/alerts` | optional `since`; `lat` and `lon` must appear together | 200. Coordinate evaluation returned no alerts **and** two provider failures; `evaluation.sources_failed` and `checked_at` make clear this was not an all-clear. Flutter retains these fields behind progressive disclosure instead of reducing the response to an empty list |
| `POST /api/v1/alerts/simulate` | `{type, lat, lon}`; enabled only with `ORCA_DEMO_MODE=1` | 200 in the explicit demo-mode audit; result had `simulated:true`, demo prefix, and demo source. Default production mode returns 403 |
| `POST /api/v1/chat` | `{message, lat, lon, date?, include_gfw?, lang?}` | 200; deterministic routing/agent execution worked and scientific absence was retained. Ollama is optional enrichment, not required for this route |
| `POST /api/v1/feedback` | arbitrary JSON object | 200; appended timestamped JSONL locally. This is not Supabase/cloud persistence |
| `GET /api/live/stream` | SSE; optional `Last-Event-ID` header | Bounded connection passed; `connected` frame and active simulated-alert replay passed, including the unknown/expired-ID path. Replay is active alerts in memory, not durable history |
| `WS /ws/chat` | JSON events; `{type:"ping"}` supported | WebSocket ping/pong passed; a full chat produced 28 routing/agent-step/token/final events and ended in `chat.final`. It used the same backend pipeline and retained provider failures |

### ORCA Live beacon/rescue endpoints

These are local in-memory Phase-1 coordination features, not AIS, Coast Guard,
Supabase, or a durable emergency dispatch service. Silence expires records and
`stop` deletes the session.

| Endpoints | Bodies/params | Test result |
|---|---|---|
| `POST /api/v1/live/start`, `POST /api/v1/live/ping`, `POST /api/v1/live/sos`, `POST /api/v1/live/sos/clear`, `POST /api/v1/live/stop` | session/position payloads described by OpenAPI | Passed end-to-end |
| `GET /api/v1/live/nearby`, `GET /api/v1/live/sos`, `GET /api/v1/live/boat/{pid}`, `GET /api/v1/live/stats` | coordinates/radius or public boat id as applicable | Passed end-to-end |
| `POST /api/v1/live/rescue/answer`, `POST /api/v1/live/rescue/complete`, `POST /api/v1/live/rescue/msg` | `{session, case_id, ...}` | Separate two-boat drill passed: SOS dispatch → rescuer receives case → accepts → sends message → completes case |

## 4. Deterministic decision boundaries

These are **ORCA Phase-1 configured policy thresholds**, not universal
vessel limits and not an IMD/INCOIS navigation certificate. WMO weather codes
and the 34 kn gale term are provider/meteorological conventions; operational
use still requires the latest official bulletin and skipper judgement.

| Signal | Below configured caution | Caution | No-go |
|---|---:|---:|---:|
| wave now / 48 h maximum | `< 2.5 m` | `>= 2.5 m` | `>= 4.0 m` |
| sustained wind, 48 h maximum | `< 20 kn` | `>= 20 kn` | — |
| gust, now / 48 h maximum | `< 28 kn` | `>= 28 kn` | `>= 34 kn` |
| daily rain total | `< 35 mm` | `>= 35 mm` | `>= 64.5 mm` |
| regional cyclone distance, when the supplemental JTWC check completes | `>= 800 km` | `< 800 km` | `< 300 km` |

Additional fail-safe rules:

- A single-point `go` requires wave, sustained wind, gust, daily weather-code,
  and completed regional cyclone evidence.
- A safe window requires wave, wind, and gust at every included hour.
- A route point is `good` only with complete wave/wind/gust evidence.
- Zero known route points reduce to `unknown`.
- Known danger/no-go evidence still takes precedence when another source is missing.
- Land-mask `false` means blocked; mask unavailable means unverified, never safe.
- Chlorophyll and SST are context. They do not independently produce HAB,
  ecological-health, species, PFZ, catch, or safety verdicts.
- Authoritative EEZ/MPA/restricted-zone polygons are not integrated. The GIS
  agent therefore makes no legal boundary or fishing-restriction assertion.

## 5. Provenance, freshness, and caching

| Data/cache | Current behaviour |
|---|---|
| Zone snapshot / advisory | In-memory keyed TTL; responses list used and failed sources |
| Point forecast | 30-minute in-memory TTL by rounded location |
| Field and route advisory | 30-minute in-memory TTL |
| Last-known-good provider values | Up to 6 hours for supported providers; labels stale age and retains the current request failure. Undated scientific values are unusable; auth/quota errors are not hidden by stale GFW data |
| NOAA analysis lag | Requested date, then explicit 3-day/7-day fallback attempts where applicable; actual analysis date is returned |
| INCOIS LAS chlorophyll | Nearest decoded observation within seven days of the request; actual selected date is returned. Missing/unparseable time coordinates and undated cached results are unusable |
| OSM/OpenSeaMap display tiles | Separate disk caches honour upstream cache-control; a stale fallback is `no-cache` |
| Flutter advisory/reason/map cache | Scientific age is calculated from the original backend timestamp; local cache-write time is only a fallback for legacy payloads that had no source timestamp |
| Feedback | Local `data/feedback.jsonl`; runtime file is ignored by Git |
| Live beacon/SSE alerts | Memory only; not durable replay/cloud storage |

Every important returned observation should carry source and observation/
retrieval time either on the value or its enclosing provider block. Cached
values must remain labelled with age. Missing values remain absent/`null`.

## 6. Final validation evidence

Measured on 2026-09-12 after restarting the edited backend:

- Python: `307 passed, 1 skipped, 3 deselected` for the complete non-live
  suite. The only warning is the existing NumPy/native binary-size warning in
  `test_extractors.py`; dependency resolution itself passes `pip check`.
- HTTP: all 24 production contract calls returned their intended statuses
  (19 successful contracts, two intentional 400 guards, one intentional 403
  drill guard, and two explicit upstream tile 502 responses).
- Streaming/coordination: bounded SSE connected; WebSocket ping plus a full
  28-event agent chat ended in `chat.final`; the two-boat rescue lifecycle
  completed and left zero active SOS records. A separate opt-in demo-mode run
  verified labelled simulated-alert creation and SSE replay semantics.
- Web: ESLint, TypeScript, Next.js production build, and `npm audit` passed;
  the audit reported zero vulnerabilities.
- Flutter: localization key/placeholder parity and presentation/domain
  boundary scans passed. Flutter/Dart tooling is unavailable in this runtime,
  so `flutter analyze`, `flutter test`, and an APK build were **not run** and
  are not claimed.
- Credentials: `GFW_API_TOKEN`, `MOSDAC_USERNAME`, and `MOSDAC_PASSWORD` were
  absent. Authenticated GFW/MOSDAC checks therefore remain untested. Forced
  open-provider requests produced the exact failures in section 2 rather than
  fabricated observations.

## 7. Reproduce the checks

```bash
# Start the single backend authority
PYTHONPATH=. .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Non-probing configuration/capability report
curl -sS http://localhost:8000/api/v1/health

# Offshore water control point; expect values OR explicit failures, never fixtures
curl -sS "http://localhost:8000/api/v1/advisory?lat=20.9&lon=69.8&include_gfw=false"
curl -sS "http://localhost:8000/api/v1/route-advisory?from_lat=20.9&from_lon=69.8&to_lat=20.7&to_lon=69.4"
curl -sS "http://localhost:8000/api/v1/alerts?lat=20.9&lon=69.8"

# Local deterministic GLOBE route check
curl -sS "http://localhost:8000/api/v1/route-check?from_lat=20.9&from_lon=69.8&to_lat=20.7&to_lon=69.4"
```

Do not use the old `20.90,70.37` harbour coordinate as an offshore control:
the bundled GLOBE mask classifies it as land. `20.90,69.80` is the audited
water control.

## 8. Bottom line

- **Are the named services real?** Mostly yes. Nominatim and INCOIS ERDDAP are
  real services but are not connected as previously claimed.
- **Are all real services wired?** No.
- **Are all wired services configured?** No: GFW and MOSDAC credentials are absent.
- **Did all wired services return live data here?** No: every forced remote
  provider attempt failed in this runtime; only local GLOBE succeeded.
- **Does the backend degrade honestly?** The audited paths now return explicit
  failures and conservative `unknown`/empty results rather than fabricated
  observations or false all-clears. OSM returns 502 when no tile is available.
