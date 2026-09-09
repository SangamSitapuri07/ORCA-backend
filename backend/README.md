# ORCA Backend

FastAPI service that exposes the ORCA data layer + 6 multi-agent
reasoning system over HTTP for the Next.js frontend.

## Quick start

```bash
# 1. Install (one-time)
pip install -r requirements.txt

# 2. Set the GFW token (optional but recommended)
export GFW_API_TOKEN="your-token-from-globalfishingwatch.org"

# 3. Run
python -m uvicorn backend.main:app --reload --port 8000
```

Then open `http://localhost:8000/docs` for the Swagger UI.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Service metadata |
| GET | `/api/v1/health` | Health check + source status |
| GET | `/api/v1/datasets` | List all data sources + agents |
| GET | `/api/v1/zones` | 8 curated Indian coastal demo zones |
| GET | `/api/v1/zone` | One ZoneSnapshot (lat, lon, date) |
| GET | `/api/v1/grid` | Grid of ZoneSnapshots (bbox + step) |
| GET | `/api/v1/reason` | Full multi-agent insight |

## Architecture

```
HTTP request
  ↓
FastAPI route handler
  ↓
pipeline.orca_data.zone_snapshot(lat, lon, date)
  ↓
  ├─ Open-Meteo (SST + waves)
  ├─ NOAA ERDDAP (chlorophyll)
  ├─ INCOIS LAS (backup chlorophyll)
  └─ GFW AIS (fishing hours + fleet)
  ↓
  ZoneSnapshot dict
  ↓
pipeline.reasoner.reason(snapshot)
  ↓
  ├─ ocean agent
  ├─ satellite agent
  ├─ fisheries agent
  ├─ marine_ecology agent
  ├─ marine_risk agent
  └─ validation agent
  ↓
  {agents, overall_risk, summary, recommendation}
  ↓
JSON response
```

## Configuration

| Env var | Purpose | Default |
|---------|---------|---------|
| `GFW_API_TOKEN` | Global Fishing Watch API token | unset (GFW calls skipped) |
| `MOSDAC_USERNAME` | MOSDAC account (Indian 🇮🇳) | unset |
| `MOSDAC_PASSWORD` | MOSDAC password | unset |

## Production notes

- The CORS config currently allows `*` — restrict this in production
- The grid endpoint guards against overly large grids (max 100 points
  with GFW enabled) but can still take many seconds for big bboxes
- The zone endpoint with `include_gfw=true` makes 2 GFW API calls
  (effort + fleet), so budget ~3-5 seconds per request
