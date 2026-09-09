"""ORCA FastAPI backend — exposes the unified data layer, 10 agents,
the deterministic advisory engine and the chat trace over HTTP+WebSocket
for the Next.js frontend.

Endpoints:
  GET  /                        health check + endpoint map
  GET  /api/v1/health           service health
  GET  /api/v1/zone             ZoneSnapshot for one lat/lon
  GET  /api/v1/grid             grid of ZoneSnapshots for a bbox
  GET  /api/v1/reason           full multi-agent reasoning for one zone
  GET  /api/v1/datasets         data sources + agent registry status
  GET  /api/v1/zones            curated demo zones
  GET  /api/v1/agents           agent registry (roles, sources, status)
  GET  /api/v1/advisory         deterministic GO/CAUTION/NO-GO advisory card
  GET  /api/v1/layers           GeoJSON layers (official PFZ, cyclones, ports, EEZ)
  GET  /api/v1/alerts           current alerts (live-evaluated for a point)
  POST /api/v1/alerts/simulate  honestly-labelled DEMO alert (disaster drill)
  POST /api/v1/chat             rule-based assistant, one-shot JSON
  POST /api/v1/feedback         store user feedback (JSONL on disk)
  WS   /ws/chat                 live chat trace (routing → agent steps →
                                tokens → final advisory) + alert.push

Run locally:
  python -m uvicorn backend.main:app --reload --port 8000
The Next.js dev server proxies /api/* to it (see web/next.config.mjs).
The WebSocket connects directly to this port (see web/lib/orca-client.ts).
"""
from __future__ import annotations

import asyncio
import faulthandler
import json
import os
import platform
import sys
import traceback
from datetime import date as date_cls
from pathlib import Path
from typing import Any


# ── Crash forensics ──
# On the laptop we saw the backend die mid-request with NO traceback
# (proxy only said "socket hang up"). That signature means a NATIVE
# crash (segfault/abort inside a C library), which Python never prints.
# faulthandler dumps the exact Python stack on SIGSEGV/SIGABRT/SIGFPE —
# to the terminal AND to logs/orca-fault.log so the evidence survives
# even if the terminal window closes. Zero cost when nothing crashes.
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
try:
    _fault_file = open(_LOG_DIR / "orca-fault.log", "a", buffering=1, encoding="utf-8")
    faulthandler.enable(file=_fault_file)
except OSError:  # read-only fs — fall back to stderr
    faulthandler.enable()
print(
    f"[ORCA] python={sys.version.split()[0]} os={platform.system()} "
    f"pid={os.getpid()} fault-log={_LOG_DIR / 'orca-fault.log'}",
    flush=True,
)


def _warn_if_port_busy(port: int = 8000) -> None:
    """Windows gotcha: SO_REUSEADDR lets TWO uvicorns bind port 8000 at the
    same time there. Then each accepts some of the connections — half your
    requests go to a stale/zombie backend and you see random 'socket hang
    up' in Next.js. Detect it: if port 8000 already answers before we bind,
    scream loudly instead of failing silently."""
    import socket
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/health", timeout=2
        ) as resp:
            if resp.status == 200:
                print(
                    f"[ORCA] ⚠️  WARNING: a backend is ALREADY answering on "
                    f"port {port} (pid {os.getpid()} is starting anyway).\n"
                    f"[ORCA] ⚠️  On Windows this splits requests between two "
                    f"backends → random socket hang-ups.\n"
                    f"[ORCA] ⚠️  Kill it first:  Get-Process python | Stop-Process -Force",
                    flush=True,
                )
    except Exception:  # noqa: BLE001 - anything failing means port is free
        return


_warn_if_port_busy()


# ── Auto-load .env file (if it exists) ──
# Lets the user put GFW_API_TOKEN / MOSDAC_USERNAME / MOSDAC_PASSWORD
# in a .env file once and have the backend pick them up automatically.
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().strip('"').strip("'")
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(PROJECT_ROOT / ".env")
_load_dotenv(PROJECT_ROOT.parent / ".env")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from pipeline import alerts as alerts_mod
from pipeline import chat as chat_mod
from pipeline import layers as layers_mod
from pipeline.advisory import build_advisory
from pipeline.orca_data import zone_snapshot, zone_snapshot_cached, grid_snapshot, INDIAN_COASTAL_ZONES


def _gfw_default(client_value: Any = None) -> bool:
    """GFW deep data default: ON when a real token is configured, unless
    the client explicitly said otherwise. The token lives in .env
    (GFW_API_TOKEN) — a quick map click can stay fast (client sends
    include_gfw=false), while Ask-ORCA/chat upgrades itself to real
    fishing-effort + fleet data automatically once the token exists."""
    if client_value is not None:
        return bool(client_value)
    return bool(os.environ.get("GFW_API_TOKEN") or os.environ.get("GFW_TOKEN"))


def _with_deadline(fn, timeout_sec: float, what: str):
    """Run fn with a hard wall-clock cap. On timeout return an honest 504
    that tells the caller the work CONTINUES in the background (results
    land in the TTL caches), so a retry in a few seconds is instant.
    Saves the UI from hanging for minutes when a public API stalls on a
    slow network — happened on the laptop: /reason blew past 220 s."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn)
    try:
        return fut.result(timeout=timeout_sec)
    except FuturesTimeout:
        ex.shutdown(wait=False)
        raise HTTPException(
            status_code=504,
            detail=(f"{what} took longer than {timeout_sec:.0f}s on this network. "
                    "It is still computing in the background — retry in 10-30 "
                    "seconds and the answer comes instantly from cache."),
        )
from pipeline.reasoner import reason
from pipeline.ttlcache import cached, cache_stats


app = FastAPI(
    title="ORCA — Marine Intelligence API",
    description="Marine EcOsystem Reasoning with Collaborative Agents · SIH 2026 PS 176",
    version="0.2.0",
)


@app.exception_handler(Exception)
async def _unhandled_to_json(request, exc):  # noqa: ANN001, ANN201
    """Safety net: ANY unhandled exception (incl. response-serialization
    failures, which live outside the route's try/except) becomes a JSON
    body carrying the full traceback instead of Starlette's bare
    'Internal Server Error' text — the web UI surfaces `detail` verbatim,
    so the failure shows its own autopsy. Born 2026-09-04: laptop showed
    'API 500: Internal Server Error' with zero usable info."""
    from fastapi.responses import JSONResponse
    tb = traceback.format_exc()
    print(f"[ORCA] UNHANDLED {request.url.path}: {type(exc).__name__}: {exc}\n{tb}",
          file=sys.stderr)
    return JSONResponse(
        status_code=500,
        content={"detail": f"unhandled {type(exc).__name__}: {exc}\n{tb[-2500:]}"},
    )

# CORS: the Next.js dev proxy proved flaky on Windows (browser→:3000 proxy
# →:8000 connections RST while the DIRECT WebSocket to :8000 worked fine),
# so the web UI now calls the backend directly on localhost. Allow any
# localhost/127.0.0.1 origin (any port) plus the Arena e2b preview hosts.
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.e2b\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
)

# CORS for the Next.js dev server (and any other local frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "*",  # Arena preview proxy; tighten in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_date(d: str | None) -> None:
    if d is not None:
        try:
            date_cls.fromisoformat(d)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date: {d}, expected YYYY-MM-DD")


# ── Health & metadata ──

@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "ORCA — Marine Intelligence API",
        "version": "0.2.0",
        "sih_problem_statement": "SIH 26176 (PS 176)",
        "endpoints": [
            "/api/v1/health",
            "/api/v1/zone",
            "/api/v1/grid",
            "/api/v1/reason",
            "/api/v1/datasets",
            "/api/v1/zones",
            "/api/v1/agents",
            "/api/v1/advisory",
            "/api/v1/layers",
            "/api/v1/alerts",
            "POST /api/v1/alerts/simulate",
            "POST /api/v1/chat",
            "POST /api/v1/feedback",
            "WS /ws/chat",
        ],
    }


def _git_commit() -> str:
    """Which checkout is this backend actually running from?

    Resolved once at startup — shown in /api/v1/health + the UI header,
    so ANY screenshot self-identifies the code behind it. Born from the
    2026-09-07 loop: the user kept seeing an error string that only
    exists in old code while new fixes were already pushed — impossible
    to tell 'pull nahi hua' from 'fix kaam nahi kiya' without this.
    """
    try:
        import subprocess
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


_GIT_COMMIT = _git_commit()


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    gfw_token_set = bool(os.environ.get("GFW_API_TOKEN"))
    mosdac_set = bool(os.environ.get("MOSDAC_USERNAME") and os.environ.get("MOSDAC_PASSWORD"))
    return {
        "status": "ok",
        "version": "0.2.0",
        "build_commit": _GIT_COMMIT,
        "gfw_token_configured": gfw_token_set,
        "credentials": {
            "gfw_token_configured": gfw_token_set,
            "mosdac_configured": mosdac_set,
        },
        "data_sources": {
            "openmeteo": "live (no key)",
            "noaa_erddap": "live (no key)",
            "esa_occci": "live (no key)",
            "gfw": "live" if gfw_token_set else "needs GFW_API_TOKEN env var or .env file",
            "incois_las": "server unreliable — fallback only",
            "incois_pfz_wfs": "live — official daily PFZ advisory lines (no key)",
            "jtwc": "live — active tropical cyclone warnings (no key)",
            "mosdac": "live" if mosdac_set else "needs MOSDAC_USERNAME + MOSDAC_PASSWORD",
        },
        "cache": cache_stats(),
    }


@app.get("/api/v1/agents")
def agents_registry() -> dict[str, Any]:
    """The 10-agent registry — roles exactly as designed in the ORCA spec."""
    return {
        "agents": [
            {"id": "ocean", "name": "Ocean Analysis 🌊",
             "role": "SST, waves, currents, swell analysis and anomaly flags",
             "sources": ["Open-Meteo Marine API"], "implemented": True},
            {"id": "satellite", "name": "Satellite Analysis 🛰️",
             "role": "Chlorophyll-a, ocean colour, productivity classification",
             "sources": ["NOAA ERDDAP VIIRS DINEOF", "ESA OC-CCI", "INCOIS LAS (backup)", "MOSDAC OCM-3 (credentials)"],
             "implemented": True},
            {"id": "weather", "name": "Weather & Hazard 🌦️",
             "role": "Wind, gusts, rainfall, storm risk (WMO/IMD thresholds)",
             "sources": ["Open-Meteo Forecast (ECMWF/MeteoFrance)"], "implemented": True},
            {"id": "gis", "name": "GIS & Spatial 🗺️",
             "role": "Coastline, zones, boundaries and spatial context",
             "sources": ["GADM/Natural Earth bundles", "MarineRegions EEZ (layers)"], "implemented": True},
            {"id": "marine_ecology", "name": "Marine Ecology 🐟",
             "role": "Cross-synthesis: upwelling, bloom risk, productivity profile",
             "sources": ["synthesizes ocean + satellite + weather results"], "implemented": True},
            {"id": "fisheries", "name": "Fisheries / PFZ 🎣",
             "role": "PFZ verdict from chlorophyll + SST + fleet signals",
             "sources": ["ZoneSnapshot", "GFW AIS (optional)", "INCOIS PFZ WFS (official advisory)"],
             "implemented": True},
            {"id": "marine_risk", "name": "Marine Risk 🚨",
             "role": "Low / Moderate / High / Critical synthesized risk",
             "sources": ["synthesizes ocean + weather + hazard results"], "implemented": True},
            {"id": "anomaly", "name": "Anomaly Detection 🔍",
             "role": "Deviation vs historical baseline (SST/chl anomalies)",
             "sources": ["ZoneSnapshot statistics"], "implemented": True},
            {"id": "validation", "name": "Data Validation ✅",
             "role": "Missing / inconsistent / abnormal data QC on every snapshot",
             "sources": ["ZoneSnapshot metadata"], "implemented": True},
            {"id": "orca_reasoning", "name": "ORCA Reasoning & Orchestration 🧠",
             "role": "Coordinates all agents, resolves conflicts, final explainable insight",
             "sources": ["all agents"], "implemented": True},
        ],
        "count": 10,
    }


@app.get("/api/v1/datasets")
def datasets() -> dict[str, Any]:
    """List all data sources + the 10 agents with metadata."""
    return {
        "agents": [
            {"id": "ocean", "name": "Ocean Analysis 🌊", "implemented": True},
            {"id": "satellite", "name": "Satellite Analysis 🛰️", "implemented": True},
            {"id": "weather", "name": "Weather & Hazard 🌦️", "implemented": True},
            {"id": "gis", "name": "GIS & Spatial 🗺️", "implemented": True},
            {"id": "marine_ecology", "name": "Marine Ecology 🐟", "implemented": True},
            {"id": "fisheries", "name": "Fisheries / PFZ 🎣", "implemented": True},
            {"id": "marine_risk", "name": "Marine Risk 🚨", "implemented": True},
            {"id": "anomaly", "name": "Anomaly Detection 🔍", "implemented": True},
            {"id": "validation", "name": "Data Validation ✅", "implemented": True},
            {"id": "orca_reasoning", "name": "ORCA Reasoning 🧠 (in reasoner.py)", "implemented": True},
        ],
        "sources": [
            {
                "id": "noaa_erddap_dineof",
                "name": "NOAA ERDDAP VIIRS DINEOF (chlorophyll)",
                "kind": "satellite", "cost": "free", "auth": "none",
                "coverage": "global, 0.025° daily, 3-day delay",
                "url": "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSDINEOFDaily",
            },
            {
                "id": "openmeteo_marine",
                "name": "Open-Meteo Marine (SST + waves)",
                "kind": "weather_model", "cost": "free", "auth": "none",
                "coverage": "global, 0.08° daily, MeteoFrance model",
                "url": "https://marine-api.open-meteo.com/v1/marine",
            },
            {
                "id": "gfw_ais",
                "name": "Global Fishing Watch (AIS)",
                "kind": "vessel_tracking", "cost": "free with token", "auth": "GFW_API_TOKEN env var",
                "coverage": "global, 0.01° daily, 2012-present",
                "url": "https://gateway.api.globalfishingwatch.org/v3/4wings/report",
            },
            {
                "id": "incois_las",
                "name": "INCOIS LAS (chlorophyll backup)",
                "kind": "satellite", "cost": "free", "auth": "none",
                "coverage": "Indian Ocean, OCM-2",
                "url": "http://las.incois.gov.in/thredds/",
            },
            {
                "id": "incois_pfz_wfs",
                "name": "INCOIS PFZ advisory lines (official, daily) 🎣",
                "kind": "advisory", "cost": "free", "auth": "none",
                "coverage": "Indian coast, daily MultiLineString advisories",
                "url": "https://incois.gov.in/geoserver/PFZ_Automation/ows",
            },
            {
                "id": "jtwc_rss",
                "name": "JTWC tropical cyclone warnings",
                "kind": "advisory", "cost": "free", "auth": "none",
                "coverage": "North Indian + NW Pacific + SH, ~6-hourly",
                "url": "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss",
            },
            {
                "id": "mosdac_ocm3",
                "name": "MOSDAC OCM-3 L4 (🇮🇳 Indian daily chlorophyll)",
                "kind": "satellite", "cost": "free with credentials",
                "auth": "MOSDAC_USERNAME / MOSDAC_PASSWORD env vars",
                "coverage": "Indian Ocean, 1 km daily",
                "url": "https://www.mosdac.gov.in",
            },
        ],
    }


# ── Indian coastal zones ──

@app.get("/api/v1/zones")
def list_zones() -> dict[str, Any]:
    """Real coordinates for 8 Indian coastal zones."""
    return {"zones": INDIAN_COASTAL_ZONES, "count": len(INDIAN_COASTAL_ZONES)}


# ── Core endpoints (v0.1, unchanged) ──

@app.get("/api/v1/zone")
def get_zone(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    date: str | None = Query(None, description="YYYY-MM-DD (default: today)"),
    radius_deg: float = Query(0.5, ge=0.05, le=5.0),
    include_gfw: bool = Query(True),
) -> dict[str, Any]:
    _validate_date(date)
    try:
        return zone_snapshot(lat, lon, date, radius_deg=radius_deg, include_gfw=include_gfw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"zone_snapshot failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")


@app.get("/api/v1/grid")
def get_grid(
    min_lat: float = Query(...),
    max_lat: float = Query(...),
    min_lon: float = Query(...),
    max_lon: float = Query(...),
    step_deg: float = Query(1.0, ge=0.1, le=5.0),
    date: str | None = Query(None),
    include_gfw: bool = Query(False),
) -> dict[str, Any]:
    if min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="min_lat must be < max_lat")
    if min_lon >= max_lon:
        raise HTTPException(status_code=400, detail="min_lon must be < max_lon")
    n_pts = ((max_lat - min_lat) / step_deg + 1) * ((max_lon - min_lon) / step_deg + 1)
    if n_pts > 100 and include_gfw:
        raise HTTPException(
            status_code=400,
            detail=f"Grid too large for GFW ({int(n_pts)} points). Use include_gfw=false or smaller bbox.",
        )
    _validate_date(date)
    try:
        return grid_snapshot(min_lat, max_lat, min_lon, max_lon, date, step_deg, include_gfw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"grid_snapshot failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")


@app.get("/api/v1/reason")
def get_reason(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    date: str | None = Query(None),
    include_gfw: bool | None = Query(None, description="GFW deep data. Omit = auto (on when token configured); true/false = force"),
    agents: str | None = Query(None, description="Comma-separated agent IDs (default: all)"),
) -> dict[str, Any]:
    _validate_date(date)
    agent_list = [a.strip() for a in agents.split(",") if a.strip()] if agents else None

    gfw = _gfw_default(include_gfw)

    def _run() -> dict[str, Any]:
        # Cached snapshot: /reason, /advisory and chat for the same point
        # share one live fetch instead of each paying the full cost.
        snap = zone_snapshot_cached(lat, lon, date, include_gfw=gfw)
        insight = reason(snap, include_agents=agent_list)
        insight["snapshot"] = snap
        return insight

    try:
        return _with_deadline(_run, 110, "10-agent analysis")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"reason failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")


# ── Phase-4: deterministic advisory ──

@app.get("/api/v1/advisory")
def get_advisory(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    date: str | None = Query(None),
    include_gfw: bool | None = Query(None, description="GFW deep data. Omit = auto (on when token configured); true/false = force"),
) -> dict[str, Any]:
    """GO / CAUTION / NO-GO advisory card. Deterministic, no LLM.
    Cached 10 min per 0.01° cell so the 30-second demo flow is instant."""
    gfw = _gfw_default(include_gfw)
    _validate_date(date)
    date_norm = date or date_cls.today().isoformat()
    key = f"advisory:{lat:.2f}:{lon:.2f}:{date_norm}:{gfw}"
    try:
        return _with_deadline(
            lambda: cached(key, 600, lambda: build_advisory(lat, lon, date_norm, include_gfw=gfw)),
            110, "advisory",
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"advisory failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")


# ── Field Explorer: real sampled grid view (spots/waves/wind map) ──

@app.get("/api/v1/field")
def get_field(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict[str, Any]:
    """9x9 sampled grid of REAL chlorophyll + waves + wind around the
    point, plus productivity hotspots. Drives the Visual Explorer map.
    Cached 30 min per 0.1° centre; budgeted so a click always answers."""
    from pipeline.field_explorer import get_field as _get_field
    try:
        return _with_deadline(lambda: _get_field(lat, lon), 60, "field")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"field fetch failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")


# ── OSM tile proxy: real map tiles for the 3D ocean surface ────────
#
# The 3D view drapes REAL OpenStreetMap tiles onto its animated surface
# via a canvas texture — which requires clean CORS. On some home
# networks the public CDN's CORS headers get stripped, the canvas is
# silently tainted, WebGL refuses the texture and the scene falls back
# to flat coloured water (seen live 2026-09-07: the "red sea" bug).
# Serving the tiles from THIS backend makes them first-party and always
# CORS-clean; the disk cache means each tile is fetched from OSM once.

TILE_CACHE_DIR = Path("data") / "tiles"
_TILE_HEADERS = {"User-Agent": "ORCA-SIH-2026/1.0 (student marine demo; interactive single-user map)"}


@app.get("/api/v1/route-check")
def route_check(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lon: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lon: float = Query(..., ge=-180, le=180),
) -> dict[str, Any]:
    """Is a straight course A->B water-only? Samples the rhumb line every
    2 km against the real GLOBE 1 km land mask; if land blocks it, one
    REAL computed detour waypoint is tried (multi-angle, growing radii).
    Never invents a safe line: ok=True/False/None(unverified) — the UI
    shows exactly which. Local math only, no network, no map-routing
    engine (there is no road graph at sea — marine navigation IS a
    course line, which is what we verify)."""
    from pipeline.routecheck import compute_sea_route
    try:
        return compute_sea_route(from_lat, from_lon, to_lat, to_lon)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"route check failed: {type(e).__name__}: {e}")


@app.get("/api/v1/route-advisory")
def route_advisory(
    from_lat: float = Query(..., ge=-90, le=90),
    from_lon: float = Query(..., ge=-180, le=180),
    to_lat: float = Query(..., ge=-90, le=90),
    to_lon: float = Query(..., ge=-180, le=180),
) -> dict[str, Any]:
    """Whole-route safe/unsafe verdict: land-verified course sampled
    every ~30 km, live marine forecast per sample point (fetched in
    parallel, 30-min cached), folded to go/caution/nogo/unknown with
    the exact thresholds the single-point advisory uses. Per-point
    rows carry the observed numbers — evidence, not adjectives."""
    from pipeline.ttlcache import cached
    from pipeline.routeadvisory import route_advisory as compute
    key = f"rtadv:{from_lat:.3f}:{from_lon:.3f}:{to_lat:.3f}:{to_lon:.3f}"
    try:
        return cached(key, 1800, lambda: compute(from_lat, from_lon, to_lat, to_lon))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"route advisory failed: {type(e).__name__}: {e}")


@app.get("/api/v1/tiles/{z}/{x}/{y}.png")
def osm_tile(z: int, x: int, y: int):
    """Cached OpenStreetMap raster tile (PNG)."""
    import urllib.request
    from fastapi.responses import FileResponse

    n = 1 << z if 0 <= z <= 19 else 0
    if not n or not (0 <= x < n and 0 <= y < n):
        raise HTTPException(400, "bad tile coordinates")
    p = TILE_CACHE_DIR / str(z) / str(x) / f"{y}.png"
    if not p.exists():
        req = urllib.request.Request(
            f"https://tile.openstreetmap.org/{z}/{x}/{y}.png", headers=_TILE_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                blob = r.read()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"OSM tile fetch failed: {type(e).__name__}: {e}")
        if not blob.startswith(b"\x89PNG"):
            raise HTTPException(502, "OSM tile server returned a non-PNG response")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".png.tmp")
        tmp.write_bytes(blob)
        tmp.replace(p)
    return FileResponse(str(p), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


# ── Phase-4: GeoJSON layers ──

@app.get("/api/v1/layers")
def get_layers(
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    types: str | None = Query(None, description="Comma list: official_pfz,cyclone,port,eez"),
) -> dict[str, Any]:
    bbox_t = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            assert len(parts) == 4
            bbox_t = (parts[0], parts[1], parts[2], parts[3])
        except (ValueError, AssertionError):
            raise HTTPException(status_code=400, detail="bbox must be minLon,minLat,maxLon,maxLat")
    type_list = [t.strip() for t in types.split(",") if t.strip()] if types else None
    return layers_mod.get_layers(bbox=bbox_t, types=type_list)


# ── Phase-4: alerts ──

@app.get("/api/v1/alerts")
async def get_alerts(
    since: str | None = Query(None, description="ISO timestamp — only alerts issued after this"),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
) -> dict[str, Any]:
    """Current alerts. If lat+lon given, first evaluate REAL conditions
    there (waves/wind/rain thresholds + active JTWC cyclones) and mint
    fresh alerts for anything that crosses a threshold."""
    newly: list[dict[str, Any]] = []
    if lat is not None and lon is not None:
        newly = await asyncio.to_thread(alerts_mod.evaluate, lat, lon)
        for a in newly:
            await alerts_mod.publish(a)
    return {
        "alerts": alerts_mod.list_alerts(since),
        "count": len(alerts_mod.list_alerts(since)),
        "newly_evaluated": newly,
    }


@app.post("/api/v1/alerts/simulate")
async def simulate_alert(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a clearly-labelled DEMO alert (simulated=true, 🧪 DEMO prefix)
    so the disaster-drill flow can be shown without faking real data,
    and push it to all connected WebSocket clients."""
    kind = str(payload.get("type", "cyclone"))
    lat = float(payload.get("lat", 20.9))
    lon = float(payload.get("lon", 70.37))
    try:
        alert = alerts_mod.simulate(kind, lat, lon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await alerts_mod.publish(alert)
    return {"created": alert, "note": "Simulated alert — marked simulated=true for demos/drills."}


# ── Phase-4: chat (HTTP one-shot; WS below streams live) ──

@app.post("/api/v1/chat")
async def chat_once(payload: dict[str, Any]) -> dict[str, Any]:
    """Rule-based assistant (no LLM yet). Same events as the WebSocket,
    delivered as one JSON document — this is the HTTP fallback path."""
    message = str(payload.get("message", "")).strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    try:
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="lat and lon are required numbers")
    _validate_date(payload.get("date"))
    try:
        return await asyncio.to_thread(
            chat_mod.answer_once,
            message, lat, lon, payload.get("date"),
            _gfw_default(payload.get("include_gfw")),
            payload.get("lang"),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"chat failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")


# ── Phase-4: feedback (stored, not dropped) ──

@app.post("/api/v1/feedback")
def post_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist fisher feedback to data/feedback.jsonl (one JSON per line)."""
    records_dir = PROJECT_ROOT / "data"
    records_dir.mkdir(exist_ok=True)
    from datetime import datetime, timezone
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": payload,
    }
    with open(records_dir / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"stored": True, "record": record}


# ── Phase-4: WebSocket chat trace + alert push ──

@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    """Blueprint contract:
      client → {"type":"chat.user_message","message":str,"lat":f,"lon":f,"lang":?}
      server → chat.routing → chat.agent_step×N → chat.token×N → chat.final
      server → alert.push (any time, when an alert is minted)
    """
    await ws.accept()
    push_q = alerts_mod.subscribe()

    async def _publisher() -> None:
        try:
            while True:
                ev = await push_q.get()
                await ws.send_json(ev)
        except Exception:  # noqa: BLE001
            pass

    pub_task = asyncio.create_task(_publisher())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "chat.error", "payload": {"error": "invalid JSON"}})
                continue

            if msg.get("type") != "chat.user_message":
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
                continue

            try:
                message = str(msg.get("message", "")).strip()
                lat = float(msg.get("lat"))
                lon = float(msg.get("lon"))
                if not message:
                    raise ValueError("empty message")
            except (TypeError, ValueError):
                await ws.send_json({"type": "chat.error",
                                    "payload": {"error": "need message, lat, lon"}})
                continue

            date = msg.get("date")
            include_gfw = _gfw_default(msg.get("include_gfw"))
            lang = msg.get("lang")

            loop = asyncio.get_running_loop()
            ev_q: asyncio.Queue = asyncio.Queue()
            done = object()

            def _produce() -> None:
                try:
                    for ev in chat_mod.stream_events(
                        message, lat, lon, date, include_gfw, lang,
                    ):
                        loop.call_soon_threadsafe(ev_q.put_nowait, ev)
                except Exception as e:  # noqa: BLE001
                    loop.call_soon_threadsafe(ev_q.put_nowait, {
                        "type": "chat.error",
                        "payload": {"error": f"{type(e).__name__}: {e}"},
                    })
                finally:
                    loop.call_soon_threadsafe(ev_q.put_nowait, done)

            worker = asyncio.create_task(asyncio.to_thread(_produce))
            while True:
                ev = await ev_q.get()
                if ev is done:
                    break
                await ws.send_json(ev)
                if ev.get("type") == "chat.token":
                    await asyncio.sleep(0.03)  # token pacing for the UI
            await worker
    except WebSocketDisconnect:
        pass
    finally:
        alerts_mod.unsubscribe(push_q)
        pub_task.cancel()


# ── Pre-import heavy native libs on the MAIN thread ──
# numpy/xarray do one-time native init at import; two worker threads
# hitting that init simultaneously (parallel source gather) has crashed
# a Windows laptop hard. Import once here so workers only ever touch
# already-initialised modules. Optional deps — absence is fine.
try:
    import numpy  # noqa: F401
    import xarray  # noqa: F401
except ImportError:
    pass

# ── Startup cache warm-up ──
# First-touch of INCOIS PFZ WFS (~5 s), JTWC (~3 s) and the default
# advisory (~60 s, Gujarat demo zone) would otherwise slow down the
# judge's very first click. Fire them in background threads so the
# endpoint answers from warm cache instead.
@app.on_event("startup")
def _warm_caches() -> None:
    import threading

    def _warm() -> None:
        import os as _os
        import time as _time
        try:
            from pipeline import incois_pfz, jtwc
            incois_pfz.get_lines()
        except Exception:  # noqa: BLE001
            pass
        try:
            jtwc.get_active_cyclones()
        except Exception:  # noqa: BLE001
            pass
        try:
            build_advisory(20.9, 70.37)  # Veraval / Gujarat demo zone
        except Exception:  # noqa: BLE001
            pass
        # Pre-warm the 8 quick-start pins (snapshots only, gentle 3 s gap)
        # so the FIRST click in a demo is instant instead of a 20-90 s
        # cold fetch. Background daemon — requests are never blocked on it.
        # ORCA_PREWARM=0 disables (slow networks / metered connections).
        if _os.environ.get("ORCA_PREWARM", "1") == "1":
            # GFW free-tier quota is precious: only the first N pins warm
            # WITH fishing data (default 3 ≈ 6 API calls); the rest warm
            # climate-only and load GFW lazily on real clicks (then it's
            # served from the 6 h cache). Override: ORCA_PREWARM_GFW_PINS.
            try:
                gfw_pins = max(0, int(_os.environ.get("ORCA_PREWARM_GFW_PINS", "3")))
            except ValueError:
                gfw_pins = 3
            for i, z in enumerate(INDIAN_COASTAL_ZONES):
                try:
                    want_gfw = bool(_gfw_default(None)) and i < gfw_pins
                    zone_snapshot_cached(z["lat"], z["lon"], include_gfw=want_gfw)
                except Exception:  # noqa: BLE001
                    pass
                _time.sleep(3)

    threading.Thread(target=_warm, daemon=True, name="cache-warmer").start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
