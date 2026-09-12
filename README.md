# ORCA — Integrated Marine Safety System

ORCA (**Marine EcOsystem Reasoning with Collaborative Agents**) is an ORCA Box-first safety system for fishers. This repository now contains one authoritative FastAPI backend, a genuine Flutter Android client, and the existing Next.js judge/rescue console.

> **Responsibility split:** Flutter APK = interface · ORCA Box = brain · Supabase = optional Phase-2 cloud memory. Safety-critical computation never depends on Supabase or an LLM.

## What is integrated

```text
Flutter widgets
  → Riverpod provider → use case → repository → Dio/SSE datasource
  → FastAPI ORCA Box
  → provider adapters + GIS + deterministic ten-agent specialist pipeline
  → deterministic marine-risk/advisory engine
  → optional bounded Ollama explanations
  → provenance-rich JSON → Flutter

Next.js console → same-origin /api proxy → the same FastAPI backend
```

The reasoning response contains ten deterministic specialist stages plus an eleventh orchestrator stage. Ollama can explain already-computed evidence, but cannot alter measurements, thresholds, GIS results, risk, recommendations, or the skipper advisory.

### Honest capability status

| Capability | Current status |
|---|---|
| Deterministic advisory, route checks, agent reasoning, GIS layers, alerts, SSE | Integrated |
| Open-Meteo, NOAA, ESA, INCOIS, JTWC provider adapters | Fetch on demand; each response reports used and failed sources |
| GFW and MOSDAC | Optional; disabled without environment credentials |
| Ollama | Optional local explanation layer with deterministic fallback |
| Web `/live` rescue subsystem | Included as the existing in-memory implementation |
| RAG | **Unavailable:** authoritative teammate implementation was not supplied |
| PostgreSQL/PostGIS | **Unavailable:** authoritative schema/repository implementation was not supplied |
| Supabase auth/history/catch/fleet aggregation | **Unavailable:** seeded records and simulated sync were removed; core safety remains available |

Unavailable components are reported by `/api/v1/health`; they are not replaced with fabricated data.

## Prerequisites

- Python 3.11+
- Node.js 20.9+ and npm (Node 22 is supported)
- Ollama only if local language explanations are wanted
- Flutter compatible with Dart 3.11 / Flutter 3.38.4+, JDK 17, and Android SDK 36 for Android builds

## 1. Start the ORCA Box backend

```bash
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m pip install -r backend/requirements.txt
python -m pip install -r pipeline/requirements.txt
cp .env.example .env                     # optional; do not commit .env
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Health and configuration:

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/ollama/health
```

### Backend environment variables

| Variable | Purpose |
|---|---|
| `GFW_API_TOKEN` | Enables Global Fishing Watch requests |
| `MOSDAC_USERNAME`, `MOSDAC_PASSWORD` | Enable authenticated MOSDAC ingestion |
| `OLLAMA_ENABLED` | `auto` by default; set `0` to disable |
| `OLLAMA_HOST` | Ollama server URL; default `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | Installed local model; default `qwen3:8b` |
| `OLLAMA_TIMEOUT_S` | Per-generation wall timeout |
| `ORCA_CORS_ORIGINS` | Comma-separated browser origins |
| `ORCA_CORS_ORIGIN_REGEX` | Optional additional browser-origin regex |
| `ORCA_DEBUG` | `1` exposes endpoint diagnostics; keep `0` in production |
| `ORCA_DEMO_MODE` | `1` enables the clearly labelled alert-drill endpoint; default `0` |
| `ORCA_WARMUP` | `1` opts into network/cache warm-up; default is off |
| `ORCA_PREWARM`, `ORCA_PREWARM_GFW_PINS` | Optional warm-up scope and GFW quota use |

## 2. Start the Next.js judge/rescue console

```bash
cd web
cp .env.example .env.local
npm ci
npm run dev -- --hostname 0.0.0.0
```

`ORCA_BACKEND_URL` is read by the Next.js server and defaults to the local backend. Browser code uses relative `/api` requests, so no backend deployment address is embedded in the client bundle. Use `NEXT_PUBLIC_ORCA_API_URL` or `NEXT_PUBLIC_ORCA_WS_URL` only when deliberately exposing FastAPI directly.

Production checks:

```bash
npm run lint
npm run typecheck
npm run build
npm audit --audit-level=moderate
```

## 3. Run the Flutter Android client

```bash
cd frontend
flutter pub get
flutter gen-l10n
flutter analyze
flutter test
flutter run --dart-define=ORCA_API_BASE_URL=https://your-orca-box.example
```

For an emulator or trusted LAN during **debug only**, inject its HTTP URL using the same `--dart-define`. Release builds target API 36, retain Android's HTTPS-only default, and are not signed with debug keys. The first-run screen also accepts an ORCA Box URL; release mode validates HTTPS.

No Supabase URL or key is currently accepted because there is no authoritative Phase-2 repository/auth implementation to connect safely.

## API surfaces used by the clients

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Honest source/component configuration status |
| `GET /api/v1/zone` | Provenance-rich point snapshot |
| `GET /api/v1/advisory` | Authoritative deterministic `go/caution/no_go/unknown` verdict |
| `GET /api/v1/reason` | Ten specialists plus orchestrator trace and optional Ollama text |
| `GET /api/v1/layers` | PFZ, cyclone, harbour, and EEZ GeoJSON |
| `GET /api/v1/route-check` | Three-state GLOBE land verification and computed sea legs |
| `GET /api/v1/route-advisory` | Per-point transit evidence and safe-window result |
| `GET /api/v1/alerts` | Active alert envelope and coordinate evaluation |
| `POST /api/v1/alerts/simulate` | Explicit demo drill only |
| `GET /api/live/stream` | SSE active-alert replay, pushes, and heartbeats |
| `/api/v1/live/*` | Existing opt-in rescue/beacon subsystem used by web `/live` |

A lack of live wave/wind/weather/cyclone evidence can never become a green advisory: the deterministic engine returns `unknown` with an explicit missing-evidence reason.

## Tests

Backend offline suite:

```bash
source .venv/bin/activate
python -m pip install pytest
python -m compileall -q backend pipeline
python -m pytest pipeline/tests -q
```

Basic local end-to-end smoke test after both servers are running:

```bash
curl -f http://127.0.0.1:8000/api/v1/health
curl -f 'http://127.0.0.1:8000/api/v1/layers?types=port'
curl -f http://127.0.0.1:3000/api/v1/health   # Next.js same-origin proxy
curl -f http://127.0.0.1:3000/live
```

Provider tests marked live/network-dependent are intentionally opt-in; provider failures must appear in response provenance rather than being converted into values. See `docs/API-GUIDE.md`, `docs/SYSTEM_DESIGN.md`, and `RUNBOOK.md` for deeper endpoint and operational notes.

## Security and data rules

- Never commit `.env`, provider tokens, credentials, signing keys, or deployment addresses.
- Keep `ORCA_DEBUG=0` in production; stack traces remain in ORCA Box logs.
- OSM is visibly attributed and used as a general base map, not an official nautical chart.
- Cached observations retain original timestamps and staleness. Missing values stay null.
- RAG context, when implemented later, must remain distinct from live scientific observations.
