# ORCA — Real Build Plan (wwith-web branch)

> **This document is the single source of truth for what we're building.**
> We update it after every milestone so we never lose the thread.

## Problem

**SIH 2026 — PS 176 (SIH26176)**
**ORCA Marine EcOsystem Reasoning with Collaborative Agents**
Organization: **ISRO** / Department of Space · Theme: Disaster Management
Idea submission deadline: **20 September 2026**

(Pinned full text in `docs/PS_176_ORCA.md`.)

## What we have access to (confirmed)

| Source | Type | Access |
| --- | --- | --- |
| **MOSDAC** (ISRO) | Satellite Earth observation files (OCEANSAT-3 OCM, SSTM, OSCAT, etc.) | ✅ Account approved, credentials in `MOSDAC_USERNAME` / `MOSDAC_PASSWORD` env vars |
| **INCOIS** | Operational ocean advisories (PFZ, high-wave, tsunami, tide) | ⏳ To be set up (public web + API) |
| **Open-Meteo** | Free weather + marine forecast, no key | ✅ Already integrated in prototype |

## What we already built (kept in `mvp-prototype` branch)

- Python FastAPI backend with 6 hand-built agents (planner, weather, ocean, GIS, risk, reasoner)
- Multilingual planner (EN / HI / TA)
- Real-time SSE streaming
- Mock INCOIS-style data generator
- 9 real PFZ polygons + 6 real geofence coordinates
- Flutter prototype UI (chat + OSM map + reasoning trace)
- 5/5 tests passing

## What we will build NOW (wwith-web branch)

**Stack:** Python FastAPI (data layer + agents) + Next.js (web UI)

**Why this stack:**
- Python stays — we have to anyway for MOSDAC NetCDF/HDF5 parsing
- Next.js because you chose it, and it's the right call: maps + dashboards + easy deploy

### Milestone 0 — Setup (this week)
- [x] Branch cleanup: `main`, `mvp-prototype`, `wwith-web`
- [x] Get user's MOSDAC credentials into env vars (user does this locally)
- [x] Write `pipeline/mosdac_auth.py` — single function that does the SSO login flow
- [x] Test it works once with the user's creds
- [x] Discover which MOSDAC files are available (9 datasetIds cataloged in `docs/MOSDAC_CATALOG.md`)
- [x] Receive 8 MOSDAC NetCDF files (`docs/MOSDAC_FILES_RECEIVED.md`)
- [x] NetCDF-3 / HDF5 parser working (`pipeline/parser.py`, 9 unit tests passing)

### Milestone 1 — Multi-source data layer ✅ DONE
- [x] `pipeline/erddap_chl.py` — NOAA ERDDAP DINEOF chlorophyll (FREE, no key, verified by user)
- [x] `pipeline/incois.py` — INCOIS LAS OPeNDAP (FREE, no key, adapter ready)
- [x] `pipeline/openmeteo_sst.py` — Open-Meteo Marine API for SST + waves (FREE, no key, verified by user)
- [x] `pipeline/gfw.py` — Global Fishing Watch AIS (FREE w/ token, verified by user: 497 hrs, 3 Indian trawlers)
- [x] `pipeline/mosdac_auth.py` + `pipeline/parser.py` — MOSDAC OCM-3/SCT L4 ready (T3 grab, 8 files on disk)
- [x] 95+ unit tests passing

### Milestone 2 — 10-agent reasoning system ✅ DONE
- [x] `pipeline/agents/ocean.py` — SST + wave analysis (Agent 1)
- [x] `pipeline/agents/satellite.py` — chlorophyll interpretation (Agent 2)
- [x] `pipeline/agents/weather.py` — IMD-style via Open-Meteo (Agent 3)
- [x] `pipeline/agents/gis.py` — Indian EEZ + ports + MPAs (Agent 4)
- [x] `pipeline/agents/marine_ecology.py` — cross-cutting patterns (Agent 5)
- [x] `pipeline/agents/fisheries.py` — PFZ composite verdict (Agent 6)
- [x] `pipeline/agents/marine_risk.py` — vessel safety risk level (Agent 7)
- [x] `pipeline/agents/anomaly.py` — vs ERA5 baseline (Agent 8)
- [x] `pipeline/agents/validation.py` — data quality checks (Agent 9)
- [x] `pipeline/reasoner.py` — orchestrator + final insight (Agent 10)
- [x] All 10 agents verified live in dashboard (Chennai offshore test)

### Milestone 3 — FastAPI backend ✅ DONE
- [x] `backend/main.py` with 7 endpoints (root, health, datasets, zones, zone, grid, reason)
- [x] CORS for cross-origin requests
- [x] Pydantic validation, range checks, grid-size guard
- [x] 10 API tests passing

### Milestone 4 — Next.js web app ✅ DONE
- [x] Bootstrap Next.js 14 + TypeScript + Tailwind + react-leaflet
- [x] Page 1: **Map dashboard** — 8 Indian coastal zones, click to analyze
- [x] Side panel: overall risk, recommendation, 9-agent breakdown
- [x] Data source attribution (used vs failed)

### Milestone 5 — Demo + submission (next)
- [ ] Take a clean dashboard screenshot
- [ ] Write a one-page architecture diagram
- [ ] Update README with the final agent list
- [ ] Build a 5-min demo script
- [ ] Submit before 20 Sep 2026

### Milestone 2 — Unified data layer (NOW)
- [ ] Write `pipeline/orca_data.py` — single async interface that fans out to all 5 sources and returns a unified `ZoneSnapshot` per lat/lon
- [ ] Each ZoneSnapshot = {sst, chlorophyll, fishing_hours, fleet_by_flag, fleet_by_gear, wave_height, source_breakdown}
- [ ] Cache layer in `pipeline/cache.py` so the same bbox/day doesn't re-hit APIs
- [ ] Add a CLI `python -m pipeline.zone_snapshot LAT LON` for quick verification

### Milestone 3 — FastAPI backend (next)
- [ ] `backend/main.py` with endpoints:
  - `GET /api/v1/zone?lat=&lon=&radius=` → ZoneSnapshot
  - `GET /api/v1/grid?min_lat=&max_lat=&min_lon=&max_lon=&step=` → grid of ZoneSnapshots
  - `GET /api/v1/zone/reason?query=` → multi-agent reasoning
- [ ] CORS for Next.js dev server
- [ ] Reuse the 10 agents (ocean, satellite, weather, gis, fisheries, marine_ecology, marine_risk, anomaly, validation + ORCA reasoning) — all implemented in `pipeline/agents/`
- [ ] `/datasets` endpoint showing what data was used per answer

### Milestone 4 — Next.js web app (week 4–6)
- [ ] Bootstrap Next.js with TypeScript + Tailwind
- [ ] Page 1: **Map dashboard** — Indian coast, all 5 data layers as togglable overlays
- [ ] Page 2: **Chat** — natural language interface to the multi-agent system
- [ ] Page 3: **Datasets** — list of what we pulled, freshness indicators, quality
- [ ] Page 4: **About** — explain the architecture for judges

### Milestone 5 — Polish + research hooks (week 6–8)
- [ ] Visualizations: chlorophyll heatmap, SST contours, wind vectors, fishing density heatmap
- [ ] Export-to-PDF button for fishermen to take a copy offshore
- [ ] Mobile-responsive (works on phone in a fishing village)
- [ ] Offline mode (PWA) — important for actual deployment

### Milestone 6 — SIH submission (week 8+)
- [ ] Demo video (5 min)
- [ ] Architecture diagram (judges love diagrams)
- [ ] README with how to reproduce
- [ ] Submit before 20 Sep 2026

## Roles

- **User**: Has MOSDAC access, sets env vars locally, runs the auth script once to validate
- **Arena agent (me)**: Writes the code, sets up the architecture, helps you debug

## What I need from you next

1. **Set the env vars locally**:
   ```bash
   export MOSDAC_USERNAME="your_username"
   export MOSDAC_PASSWORD="your_password"
   ```
   Don't paste them here.

2. **Confirm you can reach mosdac.gov.in** from your machine (some college networks block it).

3. **Take 5 minutes** to log in to https://mosdac.gov.in, go to Catalog → Satellite, and tell me which products (satellites) you have access to. Just a list like "OCEANSAT-3 OCM, OCEANSAT-3 SSTM" is enough.

## What I'll do next (without needing you)

1. Write the MOSDAC auth script (login + session handling)
2. Write the downloader (config.json style, like their official mdapi)
3. Write the NetCDF/HDF5 parser
4. Test against public open datasets first (no auth needed) to make sure parsing works
