# ORCA Backend — SIH26176 (ISRO)

**Marine EcOsystem Reasoning with Collaborative Agents** — the data + intelligence
engine. FastAPI server that fetches **only real, live ocean data** (12 sources),
reasons over it with a 10-agent pipeline, and answers the skipper's actual
questions: *what is it like here? is the whole route safe? when should I leave?*

> **Honesty is the product.** No dummy data anywhere: a source that fails is
> reported with its real reason (cloud cover, timeouts, rate limits), the
> validation agent counts it, and the UI shows it — never invented values.

Frontend (Flutter app + Next.js dashboard) lives in the sister repo:
**[SangamSitapuri07/SIH](https://github.com/SangamSitapuri07/SIH)** (`wwith-web` branch).

---

## Quick start

```powershell
pip install -r backend/requirements.txt
pip install -r pipeline/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Optional credentials via `.env` (never committed): MOSDAC username/password,
Global Fishing Watch token — the server runs fine without them and says so in
`/api/v1/health`.

## What it serves

📘 **Full guide: [docs/API-GUIDE.md](docs/API-GUIDE.md)** — har external
API kahan se aata hai, kya fetch hota hai, live status, aur ORCA ke apne
endpoints ka poora hisaab.


| Endpoint | What it answers (real mechanism) |
|---|---|
| `/api/v1/health` | live status of every source, credentials, cache |
| `/api/v1/zone` · `/grid` | point / gridded snapshot of the ocean right now |
| `/api/v1/reason` | 10-agent collaborative analysis (risk, ecology, anomaly, validation…) |
| `/api/v1/advisory` | bilingual skipper advisory — WMO/IMD small-craft thresholds |
| `/api/v1/field` · `/layers` · `/tiles` | field explorer + server-rendered PNG data tiles |
| `/api/v1/route-check` | course verified every 2 km vs the real GLOBE 1 km land mask; blocked → one REAL computed detour waypoint |
| `/api/v1/voyage` | **voyage planner** — "TU analyze kar: kahan jaun?"
  today's official INCOIS PFZ lines + NOAA chlorophyll hotspots, each
  gated by live forecast at that exact spot; auditable score per card.
  **B14 crowd-spread**: ranked spots are de-scored by (a) GFW AIS fleet
  hours nearby (30 d, top-3 spots) and (b) ORCA's OWN anonymous
  community picks (0.25° cells, rolling 24 h) — the served #1 is
  remembered so the NEXT fisher is nudged to the next-best spot.
  "Sabko same jagah nahi bhejte" — every deduction listed in reasons[] |
| `/api/v1/route-advisory` | **transit verdict**: the verified course sampled every ~30 km, live marine forecast per point in parallel, folded worst-case → `go / caution / nogo / unknown` + safest departure window |
| `/api/v1/alerts` · `/agents` · `/datasets` · `/zones` · `/chat` · `/feedback` | alerts feed, agent registry, provenance, LLM chat (optional), feedback |

## Data sources (all live, all named in responses)

Open-Meteo Marine + Forecast + Daily (MeteoFrance/ECMWF) · NOAA ERDDAP
chlorophyll (today → 3-day → 7-day lag retry) · ESA OC-CCI ocean colour ·
ISRO MOSDAC OCM-3 (real login, honest 24 s wall cap) · INCOIS LAS ·
INCOIS PFZ daily official advisory lines · Global Fishing Watch effort +
fleet (token, 429-retry) · JTWC cyclone warnings · GLOBE 1 km land mask
(offline) · Nominatim search (app-side).

## Tests

```powershell
pip install pytest
python -m pytest pipeline/tests -q     # 226 passed · +9 transit-verdict rules
```

## Repo map

```
backend/       FastAPI app + endpoints (+ its requirements.txt)
pipeline/      data fetchers, agents, verdict engines, tests (226)
tools/         verify/demo scripts (live-source diagnostics)
docs/          MOSDAC guides, CHL diagnostics, research,
               API-GUIDE.md, VOYAGE-PLANNER.md (research & design)
RUNBOOK.md     full-stack run guide (sister repo has the frontends)
start-backend.ps1
```

*Built for Smart India Hackathon 2026 · Problem Statement SIH26176 (ISRO).*
