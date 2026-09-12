"""ORCA FastAPI backend — exposes the unified data layer, eleven execution stages,
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
  POST /api/v1/live/start       ORCA Live Beacon ON (anonymous AIS-style)
  POST /api/v1/live/ping        heartbeat + position (response: sos_nearby)
  POST /api/v1/live/sos         beacon RED + POST .../sos/clear "theek hoon"
  POST /api/v1/live/stop        beacon OFF = instant full delete
  POST .../live/rescue/answer   rescuer accept/decline (B19 dispatch)
  POST .../live/rescue/complete rescuer marks rescue done → victim cleared
  POST .../live/rescue/msg      ORCA Radio case-channel message (B20)
  GET  /api/v1/live/nearby      beacons within radius (distance+bearing)
  GET  /api/v1/live/sos         all ACTIVE SOS in the network
  GET  /api/v1/live/boat/{pid}  share-link: live position by public id
  GET  /api/v1/live/stats       rescue-net status + privacy policy
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
import time
import traceback
from datetime import date as date_cls, datetime, timezone
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

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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


_STARTED_MONOTONIC = time.monotonic()

app = FastAPI(
    title="ORCA — Marine Intelligence API",
    description="Marine EcOsystem Reasoning with Collaborative Agents · SIH 2026 PS 176",
    version="0.3.0",
)


@app.exception_handler(Exception)
async def _unhandled_to_json(request, exc):  # noqa: ANN001, ANN201
    """Return JSON while keeping stack traces in ORCA Box logs by default."""
    from fastapi.responses import JSONResponse
    tb = traceback.format_exc()
    print(f"[ORCA] UNHANDLED {request.url.path}: {type(exc).__name__}: {exc}\n{tb}",
          file=sys.stderr)
    detail = "Internal server error. Check ORCA Box logs for the request traceback."
    if os.getenv("ORCA_DEBUG", "0") == "1":
        detail = f"unhandled {type(exc).__name__}: {exc}\n{tb[-2500:]}"
    return JSONResponse(status_code=500, content={"detail": detail})


def _internal_failure(label: str, exc: Exception) -> HTTPException:
    """Log endpoint failures locally without exposing internals in production."""
    tb = traceback.format_exc()
    print(f"[ORCA] {label}: {type(exc).__name__}: {exc}\n{tb}", file=sys.stderr)
    detail = f"{label} failed. Check ORCA Box logs."
    if os.getenv("ORCA_DEBUG", "0") == "1":
        detail = f"{label} failed: {type(exc).__name__}: {exc}\n{tb[-2500:]}"
    return HTTPException(status_code=500, detail=detail)

# Browser origins are explicit and environment-driven. Native Flutter clients
# do not use CORS. Production deployments should set ORCA_CORS_ORIGINS and/or
# ORCA_CORS_ORIGIN_REGEX to their own HTTPS origin(s).
_cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "ORCA_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
_cors_regex = os.getenv(
    "ORCA_CORS_ORIGIN_REGEX",
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "Last-Event-ID"],
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
        "version": "0.3.0",
        "sih_problem_statement": "SIH 26176 (PS 176)",
        "endpoints": [
            "/api/v1/health",
            "/api/v1/ollama/health",
            "/api/v1/agents",
            "/api/v1/datasets",
            "/api/v1/zones",
            "/api/v1/zone",
            "/api/v1/grid",
            "/api/v1/reason",
            "/api/v1/advisory",
            "/api/v1/field",
            "/api/v1/route-check",
            "/api/v1/route-advisory",
            "/api/v1/voyage",
            "/api/v1/layers",
            "/api/v1/alerts",
            "/api/v1/alerts/simulate",
            "/api/v1/chat",
            "/api/v1/feedback",
            "/api/v1/tiles/{z}/{x}/{y}.png",
            "/api/v1/seamarks/{z}/{x}/{y}.png",
            "/api/v1/live/start",
            "/api/v1/live/ping",
            "/api/v1/live/sos",
            "/api/v1/live/sos/clear",
            "/api/v1/live/stop",
            "/api/v1/live/rescue/answer",
            "/api/v1/live/rescue/complete",
            "/api/v1/live/rescue/msg",
            "/api/v1/live/nearby",
            "/api/v1/live/boat/{pid}",
            "/api/v1/live/stats",
            "/api/live/stream",
            "/ws/chat",
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
    """Configuration/runtime health without pretending to probe every provider."""
    from pipeline import landmask
    from pipeline.ollama_client import ollama

    gfw_token_set = bool(os.environ.get("GFW_API_TOKEN") or os.environ.get("GFW_TOKEN"))
    mosdac_set = bool(os.environ.get("MOSDAC_USERNAME") and os.environ.get("MOSDAC_PASSWORD"))
    cache = cache_stats()
    source_health = {
        "open_meteo_marine": {"name": "Open-Meteo Marine", "agency": "Open-Meteo", "status": "not_probed", "latency_ms": None, "note": "Remote fetch-on-demand; not probed by health."},
        "open_meteo_forecast": {"name": "Open-Meteo Forecast", "agency": "Open-Meteo", "status": "not_probed", "latency_ms": None, "note": "Remote fetch-on-demand; not probed by health."},
        "open_meteo_daily": {"name": "Open-Meteo Daily", "agency": "Open-Meteo", "status": "not_probed", "latency_ms": None, "note": "Remote fetch-on-demand; not probed by health."},
        "open_meteo_archive": {"name": "Open-Meteo Archive", "agency": "Open-Meteo", "status": "not_probed", "latency_ms": None, "note": "Three-prior-year comparison sample fetched on demand; not climatology and not probed by health."},
        "noaa_coastwatch": {"name": "NOAA CoastWatch ERDDAP", "agency": "NOAA NESDIS", "status": "not_probed", "latency_ms": None, "note": "Remote fetch-on-demand with explicit failure reporting; not probed by health."},
        "esa_oc_cci": {"name": "ESA OC-CCI", "agency": "European Space Agency", "status": "not_probed", "latency_ms": None, "note": "Optional chlorophyll source comparison; not probed by health."},
        "isro_mosdac": {"name": "ISRO MOSDAC OCM-3", "agency": "ISRO/SAC", "status": "configured_not_probed" if mosdac_set else "disabled", "latency_ms": None, "note": "Credentials configured." if mosdac_set else "Set MOSDAC_USERNAME and MOSDAC_PASSWORD."},
        "incois_erddap": {"name": "INCOIS ERDDAP", "agency": "MoES/INCOIS", "status": "not_integrated", "latency_ms": None, "note": "Catalogued endpoint, but the current adapter found no chlorophyll dataset and does not query it."},
        "incois_las": {"name": "INCOIS LAS", "agency": "MoES/INCOIS", "status": "not_probed", "latency_ms": None, "note": "Best-effort backup; not probed by health. The 2026-09-12 audit returned a NetCDF I/O failure in this runtime."},
        "incois_pfz": {"name": "INCOIS PFZ GeoServer", "agency": "MoES/INCOIS", "status": "not_probed", "latency_ms": None, "note": "Official WFS lines fetched on demand; not probed by health."},
        "gfw_ais": {"name": "Global Fishing Watch", "agency": "Global Fishing Watch", "status": "configured_not_probed" if gfw_token_set else "disabled", "latency_ms": None, "note": "Token configured." if gfw_token_set else "Set GFW_API_TOKEN to enable AIS effort/fleet data."},
        "jtwc_cyclone": {"name": "JTWC", "agency": "US Navy", "status": "not_probed", "latency_ms": None, "note": "Cyclone bulletins fetched on demand; not probed by health."},
        "marine_regions_eez": {"name": "MarineRegions WFS", "agency": "VLIZ", "status": "not_probed", "latency_ms": None, "note": "Optional EEZ display overlay only; not legal/safety evidence and not probed by health."},
        "osm_tiles": {"name": "OpenStreetMap tiles", "agency": "OpenStreetMap", "status": "not_probed", "latency_ms": None, "note": "First-party cached display proxy; not probed by health."},
        "openseamap_seamarks": {"name": "OpenSeaMap seamarks", "agency": "OpenSeaMap", "status": "not_probed", "latency_ms": None, "note": "Optional first-party cached display proxy; not an official nautical chart and not probed by health."},
        "globe_landmask": {"name": "GLOBE 1 km Land Mask", "agency": "NOAA", "status": "available" if landmask.enabled() else "unavailable", "latency_ms": None, "note": "Bundled local raster." if landmask.enabled() else "Install global-land-mask to enable route verification."},
        "nominatim_osm": {"name": "Nominatim", "agency": "OpenStreetMap", "status": "not_integrated", "latency_ms": None, "note": "Listed in the client source catalog only; no search datasource is wired."},
    }
    return {
        "status": "ok",
        "version": "0.3.0",
        "build_commit": _GIT_COMMIT,
        "uptime_seconds": int(time.monotonic() - _STARTED_MONOTONIC),
        "gfw_token_configured": gfw_token_set,
        "credentials": {
            "gfw_token_configured": gfw_token_set,
            "mosdac_configured": mosdac_set,
        },
        # Legacy summary retained for the existing web source chips.
        "data_sources": {
            "openmeteo": "wired (remote fetch-on-demand; not probed)",
            "noaa_erddap": "wired (remote fetch-on-demand; not probed)",
            "esa_occci": "wired optional cross-check (not probed)",
            "gfw": "configured" if gfw_token_set else "disabled — needs GFW_API_TOKEN",
            "incois_las": "wired backup (remote fetch-on-demand; not probed)",
            "incois_pfz_wfs": "wired (official WFS; remote fetch-on-demand; not probed)",
            "jtwc": "wired supplemental guidance (remote fetch-on-demand; not probed)",
            "mosdac": "configured" if mosdac_set else "disabled — needs MOSDAC credentials",
        },
        "source_health": source_health,
        "components": {
            "ollama": ollama.health(probe=False),
            "sse": {"status": "available", "persistence": "in-memory active-alert replay"},
            "demo_alerts": {"status": "enabled" if os.environ.get("ORCA_DEMO_MODE", "0") == "1" else "disabled"},
            "postgres_postgis": {"status": "unavailable", "reason": "authoritative team implementation not supplied"},
            "rag": {"status": "unavailable", "reason": "authoritative team implementation not supplied"},
            "supabase": {"status": "unavailable", "reason": "no server-side route implementation supplied; core safety is independent"},
        },
        "cache": cache,
        "cache_summary": {"in_memory_keys": len(cache), "hit_rate_pct": None},
    }


@app.get("/api/v1/ollama/health")
def ollama_health() -> dict[str, Any]:
    """Actively probe the configured local Ollama server and model."""
    from pipeline.ollama_client import ollama
    return ollama.health(probe=True)


@app.get("/api/v1/agents")
def agents_registry() -> dict[str, Any]:
    """The eleven real execution stages exposed by ``/api/v1/reason``."""
    agents = [
        {"id": "data_validation", "name": "Data Validation ✅", "class": "DETERMINISTIC", "role": "Physical-range, missing-data and provenance checks", "sources": ["ZoneSnapshot metadata"]},
        {"id": "gis_spatial", "name": "GIS & Spatial 🗺️", "class": "DETERMINISTIC", "role": "GLOBE land/sea context; legal boundaries explicitly unavailable", "sources": ["GLOBE 1 km land mask", "ORCA static port references (citations pending)"]},
        {"id": "ocean_analysis", "name": "Ocean Analysis 🌊", "class": "LLM + DETERMINISTIC", "role": "Deterministic SST/wave analysis with optional Ollama explanation", "sources": ["Open-Meteo Marine"]},
        {"id": "satellite_analysis", "name": "Satellite Analysis 🛰️", "class": "LLM + DETERMINISTIC", "role": "Deterministic chlorophyll cross-check with optional Ollama explanation", "sources": ["NOAA ERDDAP", "ESA OC-CCI", "MOSDAC OCM-3"]},
        {"id": "weather_hazard", "name": "Weather & Hazard 🌦️", "class": "LLM + DETERMINISTIC", "role": "Configured weather threshold checks with optional Ollama explanation", "sources": ["Open-Meteo Forecast"]},
        {"id": "map_synoptic", "name": "Map Synoptic 🗺️", "class": "DETERMINISTIC", "role": "Available overlays with per-layer provenance and failure metadata", "sources": ["ORCA GeoJSON layer service"]},
        {"id": "marine_ecology", "name": "Marine Ecology 🐟", "class": "LLM + DETERMINISTIC", "role": "Provisional co-observation context; no ecological or catch verdict", "sources": ["ZoneSnapshot observations"]},
        {"id": "fisheries_pfz", "name": "Fisheries Context 🎣", "class": "LLM + DETERMINISTIC", "role": "Reports environmental and GFW context without inventing a PFZ verdict", "sources": ["GFW AIS", "ZoneSnapshot observations"]},
        {"id": "anomaly_detection", "name": "Anomaly Detection 🔍", "class": "DETERMINISTIC", "role": "Deviation against fetched historical baselines", "sources": ["Open-Meteo Archive"]},
        {"id": "marine_risk", "name": "Marine Risk 🚨", "class": "DETERMINISTIC", "role": "Wave/weather hazard fold; /api/v1/advisory owns the skipper verdict", "sources": ["Structured agent findings"]},
        {"id": "orchestrator", "name": "ORCA Orchestrator 🧠", "class": "LLM + DETERMINISTIC", "role": "Deterministic synthesis with optional bounded Ollama explanation", "sources": ["All agent findings"]},
    ]
    return {
        "agents": [{**agent, "implemented": True, "rag_invoked": False} for agent in agents],
        "count": len(agents),
        "safety_authority": "/api/v1/advisory deterministic engine",
        "rag_status": "unavailable — authoritative implementation not supplied",
    }


@app.get("/api/v1/datasets")
def datasets() -> dict[str, Any]:
    """Catalog every external/local source named by this checkout.

    ``integration_status`` describes code/configuration, not current provider
    liveness. Use the scientific endpoints for explicit per-request failures.
    """
    return {
        "agents": agents_registry()["agents"],
        "sources": [
            {
                "id": "noaa_erddap_dineof", "name": "NOAA CoastWatch ERDDAP",
                "kind": "satellite", "cost": "free", "auth": "none",
                "coverage": "configured VIIRS chlorophyll datasets",
                "url": "https://coastwatch.noaa.gov/erddap/",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "esa_oc_cci", "name": "ESA OC-CCI v6 via NOAA ERDDAP",
                "kind": "satellite", "cost": "free", "auth": "none",
                "coverage": "optional chlorophyll source comparison",
                "url": "https://comet.nefsc.noaa.gov/erddap/griddap/occci_v6_daily_1km",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "openmeteo_marine", "name": "Open-Meteo Marine",
                "kind": "weather_model", "cost": "free", "auth": "none",
                "coverage": "marine forecast variables used by ORCA",
                "url": "https://marine-api.open-meteo.com/v1/marine",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "openmeteo_forecast", "name": "Open-Meteo Forecast and Daily",
                "kind": "weather_model", "cost": "free", "auth": "none",
                "coverage": "wind, gust, rain, weather-code and daily context",
                "url": "https://api.open-meteo.com/v1/forecast",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "openmeteo_archive", "name": "Open-Meteo Archive",
                "kind": "historical_context", "cost": "free", "auth": "none",
                "coverage": "up to three prior-year date-window SST samples",
                "url": "https://archive-api.open-meteo.com/v1/archive",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "isro_mosdac", "name": "MOSDAC EOS-06 OCM-3 L2C LAC",
                "kind": "satellite", "cost": "free with credentials",
                "auth": "MOSDAC_USERNAME / MOSDAC_PASSWORD env vars",
                "coverage": "optional OCM-3 granule source comparison",
                "url": "https://www.mosdac.gov.in",
                "integration_status": "wired_requires_credentials",
            },
            {
                "id": "incois_erddap", "name": "INCOIS ERDDAP",
                "kind": "catalog_only", "cost": "free", "auth": "none",
                "coverage": "no selected chlorophyll dataset in current code",
                "url": "https://erddap.incois.gov.in/erddap/",
                "integration_status": "not_integrated",
            },
            {
                "id": "incois_las", "name": "INCOIS LAS chlorophyll backup",
                "kind": "satellite", "cost": "free", "auth": "none",
                "coverage": "best-effort Indian Ocean backup",
                "url": "http://las.incois.gov.in/thredds/",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "incois_pfz_wfs", "name": "INCOIS official PFZ WFS",
                "kind": "advisory", "cost": "free", "auth": "none",
                "coverage": "official PFZ line geometry",
                "url": "https://incois.gov.in/geoserver/PFZ_Automation/ows",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "gfw_ais", "name": "Global Fishing Watch v3",
                "kind": "vessel_context", "cost": "free with token",
                "auth": "GFW_API_TOKEN / GFW_TOKEN env var",
                "coverage": "optional effort and vessel/fleet context",
                "url": "https://gateway.api.globalfishingwatch.org/v3/4wings/report",
                "integration_status": "wired_requires_credentials",
            },
            {
                "id": "jtwc_rss", "name": "JTWC tropical cyclone warnings",
                "kind": "supplemental_advisory", "cost": "free", "auth": "none",
                "coverage": "supplemental regional cyclone guidance; not IMD",
                "url": "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "marine_regions_eez", "name": "MarineRegions WFS",
                "kind": "display_layer", "cost": "free", "auth": "none",
                "coverage": "optional EEZ display only; not legal evidence",
                "url": "https://geo.vliz.be/geoserver/MarineRegions/ows",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "globe_landmask", "name": "GLOBE 1 km land mask",
                "kind": "bundled_local_raster", "cost": "bundled dependency", "auth": "none",
                "coverage": "local land/water route checks",
                "url": "https://www.ngdc.noaa.gov/mgg/topo/gltiles.html",
                "integration_status": "local_component",
            },
            {
                "id": "osm_tiles", "name": "OpenStreetMap tiles",
                "kind": "display_layer", "cost": "free under usage policy", "auth": "none",
                "coverage": "first-party cached base-map proxy",
                "url": "https://tile.openstreetmap.org/",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "openseamap_seamarks", "name": "OpenSeaMap seamarks",
                "kind": "display_layer", "cost": "free", "auth": "none",
                "coverage": "optional seamark proxy; not an official nautical chart",
                "url": "https://tiles.openseamap.org/seamark/",
                "integration_status": "wired_not_probed",
            },
            {
                "id": "nominatim_osm", "name": "Nominatim search",
                "kind": "catalog_only", "cost": "free under usage policy", "auth": "none",
                "coverage": "no production search datasource in current code",
                "url": "https://nominatim.openstreetmap.org/",
                "integration_status": "not_integrated",
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
        raise _internal_failure("zone snapshot", e)


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
        raise _internal_failure("grid snapshot", e)


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
        # share one remote fetch instead of each paying the full cost.
        snap = zone_snapshot_cached(lat, lon, date, include_gfw=gfw)
        insight = reason(snap, include_agents=agent_list)
        insight["snapshot"] = snap
        return insight

    try:
        return _with_deadline(_run, 110, "11-stage agent analysis")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _internal_failure("reasoning", e)


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
        raise _internal_failure("advisory", e)


# ── Field Explorer: real sampled grid view (spots/waves/wind map) ──

@app.get("/api/v1/field")
def get_field(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict[str, Any]:
    """Sampled chlorophyll, wave and wind grids around a point.

    The compatibility ``hotspots`` field only ranks high chlorophyll cells; it
    is not a PFZ, HAB diagnosis, catch estimate, or fishing recommendation.
    Cached 30 min per 0.1° centre; source failures return explicit empty/error
    sections instead of fabricated samples.
    """
    from pipeline.field_explorer import get_field as _get_field
    try:
        return _with_deadline(lambda: _get_field(lat, lon), 60, "field")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _internal_failure("field fetch", e)


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
        raise _internal_failure("route check", e)


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
        raise _internal_failure("route advisory", e)


@app.get("/api/v1/voyage")
def voyage_recommend(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    max_km: float = Query(120.0, ge=20.0, le=400.0),
) -> dict[str, Any]:
    """Return candidate points derived only from official INCOIS PFZ lines.

    Each point carries a separate marine-weather evidence state. The numeric
    score is an explicitly experimental ordering by evidence state, distance,
    and optional crowd context; it is not an INCOIS score, catch probability,
    or safety certification. If official geometry is unavailable, returns
    ``found:false`` with the provider reason and no invented candidate.
    """
    from pipeline.ttlcache import cached
    from pipeline.voyage import recommend
    key = f"voyage:{lat:.3f}:{lon:.3f}:{max_km:.0f}"
    try:
        return cached(key, 1800, lambda: recommend(lat, lon, max_km))
    except Exception as e:  # noqa: BLE001
        raise _internal_failure("voyage", e)


# ── B18: ORCA Live Beacon — "Samudri Rakshak Net" ────────────────────
# AIS waali philosophy fisher ke phone pe: voyage ke dauraan chhota GPS
# ping → anonymous live beacon. SOS → paas ke ORCA boats ko automatic
# alert (ping ke response mein hi). Privacy by design: positions sirf
# tab tak survive karti hain jab tak ping aata rahe (2 h silence →
# auto-delete), koi identity nahi, raw session kabhi public nahi.


def _live_f(payload: dict[str, Any], key: str, lo: float, hi: float) -> float:
    v = payload.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= float(v) <= hi):
        raise HTTPException(
            status_code=400,
            detail=f"'{key}' missing/invalid — {lo}..{hi} ke beech number chahiye")
    return float(v)


def _live_session(payload: dict[str, Any]) -> str:
    v = payload.get("session")
    if not isinstance(v, str) or len(v.strip()) < 4:
        raise HTTPException(
            status_code=400,
            detail="'session' missing — pehle POST /api/v1/live/start karo")
    return v.strip()


@app.post("/api/v1/live/start")
def live_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Beacon ON — voyage shuru. Body: {lat, lon, label?, session?}.
    session na diya toh server ek random id bana ke de deta hai."""
    from pipeline import live
    lat = _live_f(payload, "lat", -90.0, 90.0)
    lon = _live_f(payload, "lon", -180.0, 180.0)
    label = payload.get("label")
    session = payload.get("session") if isinstance(payload.get("session"), str) else ""
    return live.start(session.strip(), lat, lon, label=label if isinstance(label, str) else None)


@app.post("/api/v1/live/ping")
def live_ping(payload: dict[str, Any]) -> dict[str, Any]:
    """Heartbeat + position. Response hi alert channel hai: sos_nearby +
    rescue_request (+ ORCA Radio messages) + my_sos dispatch status.
    Body: {session, lat, lon, speed_kn?, heading_deg?, label?, watch?}
    watch=true → LISTENER mode (B20): bina beacon ke bhi SOS alerts —
    position ~11 km tak ROUND ho ke store hoti hai (exact trail nahi)."""
    from pipeline import live
    session = _live_session(payload)
    lat = _live_f(payload, "lat", -90.0, 90.0)
    lon = _live_f(payload, "lon", -180.0, 180.0)

    def _opt(key: str) -> float | None:
        v = payload.get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    label = payload.get("label")
    return live.ping(session, lat, lon, speed_kn=_opt("speed_kn"),
                     heading_deg=_opt("heading_deg"),
                     label=label if isinstance(label, str) else None,
                     watch=payload.get("watch") is True)


@app.post("/api/v1/live/sos")
def live_sos_on(payload: dict[str, Any]) -> dict[str, Any]:
    """🚨 Beacon RED. Body: {session, note?, lat?, lon?}. Unknown session
    bhi lat/lon ke saath turant register ho jaata hai — zindagi-maut ke
    waqt 'pehle start karo' error kabhi nahi."""
    from pipeline import live
    session = _live_session(payload)

    def _opt(key: str) -> float | None:
        v = payload.get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    note = payload.get("note")
    res = live.sos_on(session, note=note if isinstance(note, str) else None,
                      lat=_opt("lat"), lon=_opt("lon"))
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "unknown session"))
    return res


@app.post("/api/v1/live/sos/clear")
def live_sos_off(payload: dict[str, Any]) -> dict[str, Any]:
    """'Main theek hoon' — SOS band. Body: {session}."""
    from pipeline import live
    res = live.sos_off(_live_session(payload))
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "unknown session"))
    return res


@app.post("/api/v1/live/stop")
def live_stop(payload: dict[str, Any]) -> dict[str, Any]:
    """Beacon OFF = turant poora delete (privacy promise). Body: {session}."""
    from pipeline import live
    return live.stop(_live_session(payload))


@app.post("/api/v1/live/rescue/answer")
def live_rescue_answer(payload: dict[str, Any]) -> dict[str, Any]:
    """B19 dispatch ka jawab. Body: {session, case_id, accept: bool, reason?}.
    accept → dono taraf live tracking; decline (+ wajah) → next boats ko
    jaata rahega. Accepted response mein rescuer→victim bearing/doori aati hai."""
    from pipeline import live
    session = _live_session(payload)
    case_id = payload.get("case_id")
    if not isinstance(case_id, str) or len(case_id.strip()) < 4:
        raise HTTPException(status_code=400, detail="'case_id' missing — rescue_request mein aaya tha")
    accept = payload.get("accept")
    if not isinstance(accept, bool):
        raise HTTPException(status_code=400, detail="'accept' true/false chahiye")
    reason = payload.get("reason")
    res = live.rescue_answer(session, case_id.strip(), accept,
                             reason=reason if isinstance(reason, str) else None)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "case nahi mila"))
    return res


@app.post("/api/v1/live/rescue/complete")
def live_rescue_complete(payload: dict[str, Any]) -> dict[str, Any]:
    """Rescuer: 'pahunch gaya / sab safe' → case RESOLVE + victim SOS auto-clear.
    Body: {session, case_id}. Sirf ACCEPTED rescuer kar sakta hai."""
    from pipeline import live
    session = _live_session(payload)
    case_id = payload.get("case_id")
    if not isinstance(case_id, str) or len(case_id.strip()) < 4:
        raise HTTPException(status_code=400, detail="'case_id' missing")
    res = live.rescue_complete(session, case_id.strip())
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error", "case nahi mila"))
    return res


@app.post("/api/v1/live/rescue/msg")
def live_rescue_msg(payload: dict[str, Any]) -> dict[str, Any]:
    """📻 ORCA Radio — case channel pe message (B20). Body: {session,
    case_id, text, preset?}. Sirf victim + accepted rescuer. Delivery
    ping/watch responses ke andar hi hoti hai — alag polling nahi."""
    from pipeline import live
    session = _live_session(payload)
    case_id = payload.get("case_id")
    if not isinstance(case_id, str) or len(case_id.strip()) < 4:
        raise HTTPException(status_code=400, detail="'case_id' missing")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="'text' missing — message khaali nahi ho sakta")
    res = live.rescue_msg(session, case_id.strip(), text=text.strip(),
                          preset=payload.get("preset") is True)
    if not res.get("ok"):
        raise HTTPException(status_code=403, detail=res.get("error", "msg fail"))
    return res


@app.get("/api/v1/live/nearby")
def live_nearby(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_nm: float = Query(20.0, ge=0.5, le=100.0),
) -> dict[str, Any]:
    """Radius ke andar ke saare live beacons (distance + bearing) —
    rescue radar view."""
    from pipeline import live
    return live.nearby(lat, lon, radius_nm)


@app.get("/api/v1/live/sos")
def live_sos_list() -> dict[str, Any]:
    """Poore network ke ACTIVE SOS — command-center / demo view."""
    from pipeline import live
    return live.sos_list()


@app.get("/api/v1/live/boat/{pid}")
def live_boat(pid: str) -> dict[str, Any]:
    """Share-link lookup — pub_id se live position (family/rescue)."""
    from pipeline import live
    res = live.by_pub_id(pid)
    if res is None:
        raise HTTPException(
            status_code=404,
            detail="boat nahi mili — beacon band ho gaya, expire ho gaya "
                   "(2 h silence) ya pub_id galat hai. ORCA kabhi purani "
                   "position fake nahi karta.")
    return {"ok": True, "boat": res}


@app.get("/api/v1/live/stats")
def live_stats() -> dict[str, Any]:
    from pipeline import live
    return live.stats()


@app.get("/api/v1/tiles/{z}/{x}/{y}.png")
def osm_tile(z: int, x: int, y: int):
    """OSM proxy with bounded disk cache that honours upstream max-age."""
    return _cached_png_tile(
        z,
        x,
        y,
        cache_dir=TILE_CACHE_DIR,
        upstream_url=f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        provider="OSM",
    )


@app.get("/api/v1/seamarks/{z}/{x}/{y}.png")
def openseamap_tile(z: int, x: int, y: int):
    """Optional OpenSeaMap seamark overlay proxy; not a nautical chart."""
    return _cached_png_tile(
        z,
        x,
        y,
        cache_dir=Path("data") / "seamarks",
        upstream_url=f"https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png",
        provider="OpenSeaMap",
    )


def _cached_png_tile(
    z: int,
    x: int,
    y: int,
    *,
    cache_dir: Path,
    upstream_url: str,
    provider: str,
):
    """Fetch/cache a display tile without disguising upstream failure."""
    import re
    import urllib.request
    from fastapi.responses import FileResponse, Response

    n = 1 << z if 0 <= z <= 19 else 0
    if not n or not (0 <= x < n) or not (0 <= y < n):
        raise HTTPException(400, "bad tile coordinates")
    path = cache_dir / str(z) / str(x) / f"{y}.png"
    metadata_path = path.with_suffix(".meta.json")
    metadata: dict[str, Any] = {}
    try:
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        metadata = {}

    fresh = path.exists() and float(metadata.get("expires_at", 0)) > time.time()
    if not fresh:
        request = urllib.request.Request(upstream_url, headers=_TILE_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                blob = response.read()
                cache_control = response.headers.get("Cache-Control", "public, max-age=3600")
                match = re.search(r"(?:^|,)\s*max-age=(\d+)", cache_control, re.IGNORECASE)
                no_cache = "no-cache" in cache_control.lower() or "no-store" in cache_control.lower()
                max_age = 0 if no_cache else (max(60, int(match.group(1))) if match else 3600)
                metadata = {
                    "cache_control": cache_control,
                    "expires_at": time.time() + max_age,
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except Exception as exc:  # noqa: BLE001
            print(f"[ORCA] {provider} tile fetch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            if not path.exists():
                raise HTTPException(502, f"{provider} tile fetch failed; see ORCA Box logs.")
            # A stale fallback remains labelled for revalidation rather than
            # being assigned a false fresh TTL.
            metadata["cache_control"] = "no-cache"
        else:
            if not blob.startswith(b"\x89PNG"):
                raise HTTPException(502, f"{provider} tile server returned a non-PNG response")
            if "no-store" in str(metadata.get("cache_control", "")).lower():
                return Response(
                    content=blob,
                    media_type="image/png",
                    headers={"Cache-Control": str(metadata["cache_control"])},
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".png.tmp")
            tmp.write_bytes(blob)
            tmp.replace(path)
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    headers = {"Cache-Control": str(metadata.get("cache_control", "no-cache"))}
    if metadata.get("etag"):
        headers["ETag"] = str(metadata["etag"])
    if metadata.get("last_modified"):
        headers["Last-Modified"] = str(metadata["last_modified"])
    return FileResponse(str(path), media_type="image/png", headers=headers)


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
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
) -> dict[str, Any]:
    """Current alerts. If lat+lon given, first evaluate REAL conditions
    there (waves/wind/rain thresholds + active JTWC cyclones) and mint
    fresh alerts for anything that crosses a threshold."""
    if (lat is None) != (lon is None):
        raise HTTPException(status_code=400, detail="lat and lon must be provided together")
    evaluation: dict[str, Any] | None = None
    newly: list[dict[str, Any]] = []
    if lat is not None and lon is not None:
        evaluation = await asyncio.to_thread(alerts_mod.evaluate_status, lat, lon)
        newly = evaluation["alerts"]
        for a in newly:
            await alerts_mod.publish(a)
    active = alerts_mod.list_alerts(since)
    return {
        "alerts": active,
        "count": len(active),
        "newly_evaluated": newly,
        "evaluation": ({k: v for k, v in evaluation.items() if k != "alerts"}
                       if evaluation is not None else None),
    }


@app.post("/api/v1/alerts/simulate")
async def simulate_alert(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a clearly-labelled DEMO alert (simulated=true, 🧪 DEMO prefix)
    so the disaster-drill flow can be shown without faking real data,
    and push it to all connected clients. Disabled by default."""
    if os.environ.get("ORCA_DEMO_MODE", "0") != "1":
        raise HTTPException(status_code=403, detail="Demo alert simulation is disabled on this ORCA Box.")
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
    """Deterministic agent-backed assistant with optional Ollama enrichment.

    Uses the same events as the WebSocket and retains source failures in the
    one-document HTTP fallback response.
    """
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
        raise _internal_failure("chat", e)


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


# ── Live alert stream + WebSocket chat trace ──

def _sse_frame(event: str, data: Any, *, event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    lines.extend(f"data: {line}" for line in encoded.splitlines() or [""])
    return "\n".join(lines) + "\n\n"


@app.get("/api/live/stream")
async def live_alert_stream(request: Request) -> StreamingResponse:
    """SSE alert channel with active-alert replay and heartbeat frames.

    ``Last-Event-ID`` resumes after a known active alert. Since Phase-1 alert
    storage is bounded in memory, an unknown/expired id replays every currently
    active alert rather than pretending durable replay exists.
    """
    queue = alerts_mod.subscribe()
    last_event_id = request.headers.get("last-event-id")

    async def events():
        try:
            yield _sse_frame("connected", {
                "status": "connected",
                "server_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "replay": "active alerts in memory",
            })

            active = alerts_mod.list_alerts()
            if last_event_id:
                indexes = [i for i, alert in enumerate(active) if alert.get("id") == last_event_id]
                replay = active[indexes[0] + 1:] if indexes else active
            else:
                replay = active
            for alert in replay:
                yield _sse_frame("alert.push", alert, event_id=alert.get("id"))

            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if message.get("type") == "alert.push":
                        alert = message.get("alert", {})
                        yield _sse_frame("alert.push", alert, event_id=alert.get("id"))
                except asyncio.TimeoutError:
                    yield _sse_frame("heartbeat", {
                        "server_time": datetime.now(timezone.utc).isoformat(timespec="seconds")
                    })
        finally:
            alerts_mod.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

    # Network-heavy warm-up is opt-in. This keeps normal startup deterministic
    # and avoids consuming provider quotas before a user asks for data.
    if os.environ.get("ORCA_WARMUP", "0") != "1":
        return

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
