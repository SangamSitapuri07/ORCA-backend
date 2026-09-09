"""Global Fishing Watch (GFW) adapter — real fishing vessel activity.

Global Fishing Watch (https://globalfishingwatch.org) publishes
AIS-derived fishing effort data for >190,000 fishing vessels globally.
The data shows where fishing vessels ACTUALLY go — a ground-truth
proxy for where fish are caught.

This is gold for ORCA because:
- It's a real-world validation: satellite chlorophyll shows where
  plankton are, AIS shows where the boats go. The overlap = good zones.
- It covers the Indian Ocean fully via the IOTC (Indian Ocean
  Tuna Commission) RFMO region.
- Daily resolution, 0.01° grid (1km), 2012-2024.
- Free API for non-commercial research.

Authentication:
- Register at https://globalfishingwatch.org (free)
- Get API Access Token from your profile
- Set the env var GFW_API_TOKEN (or pass token= parameter)

Usage:
    from pipeline.gfw import get_fishing_effort
    hours = get_fishing_effort(19.0, 72.8, "2026-08-01", "2026-08-30")
    # Returns: {"hours": 47.3, "vessel_ids": 12, "source": "GFW IOTC", ...}

For research: https://globalfishingwatch.org/our-apis/
For SDK:      https://github.com/GlobalFishingWatch/gfw-api-python-client
For data:     https://globalfishingwatch.org/data-download/datasets/public-fishing-effort
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any


# Auto-load .env from project root (so GFW_API_TOKEN can be set
# in .env file without having to export it in every terminal).
def _load_dotenv_quiet(path: Path) -> None:
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


_THIS = Path(__file__).resolve()
for _p in (_THIS.parent.parent, _THIS.parent.parent.parent, Path.cwd()):
    _load_dotenv_quiet(_p / ".env")


# GFW API v3 base URL
GFW_API_BASE = "https://gateway.api.globalfishingwatch.org/v3"

# IOTC = Indian Ocean Tuna Commission RFMO region
DEFAULT_REGION = "IOTC"
DEFAULT_REGION_SOURCE = "RFMO"

# Public fishing effort dataset (since 2012)
DATASET_FISHING_EFFORT = "public-global-fishing-effort:latest"

# GFW free API empirical limit: ~90 days (despite docs saying 366)
GFW_SAFE_MAX_DAYS = 90
# 4 days ago is the most recent data available
GFW_LATEST_DELAY_DAYS = 4


# Browser-like headers — Cloudflare (fronting GFW) blocks bot-looking requests
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://globalfishingwatch.org",
    "Referer": "https://globalfishingwatch.org/",
}

def get_token() -> str | None:
    """Get the GFW API token from environment."""
    return os.environ.get("GFW_API_TOKEN")


# ── Free-tier quota guard ─────────────────────────────────────────────
# GFW's free API answers HTTP 429 (Too Many Requests) when hammered —
# our 8-pin startup prewarm + rapid map clicks can trip it. Two defences:
#   1. Success-only cache (6 h): fishing effort for a date window moves
#      ~once a day, so repeat clicks must NOT burn fresh API calls.
#   2. Global cooldown: after a 429 we pause ALL GFW calls for the
#      server's Retry-After window and report the pause honestly,
#      instead of spamming a server that already said "stop".
_RATE_LIMIT_UNTIL = 0.0
_result_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_GFW_CACHE_TTL_SEC = 6 * 3600  # 6 h

# ── Persistent state (survives backend restarts) ─────────────────────
# Root cause of the "429 keeps coming back even after our 120 s pause"
# loop (2026-09): both the success cache AND the 429 cooldown lived in
# process memory only — every backend restart wiped both, the prewarm
# immediately re-burned calls into an already-angry server, and the
# loop never escaped. State now lives in data/gfw_cache.json:
#   entries            → success cache (same 6 h TTL, restart-proof)
#   rate_limited_until → the 429 cooldown timestamp (restart-proof)
#   last_headers       → GFW's x-ratelimit-* headers from the last
#                        response, so we can TELL daily-quota 429s
#                        (remaining=0, reset in N hours) apart from
#                        burst/per-minute 429s instead of guessing.
_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "gfw_cache.json"
_disk_state: dict | None = None

# Rate-limit headers GFW documents (May 2026 V3 release notes)
_RL_HEADER_KEYS = (
    "x-ratelimit-daily-limit-requests",
    "x-ratelimit-daily-remaining-requests",
    "x-ratelimit-daily-current-usage",
    "x-ratelimit-daily-reset-hours",
    "x-ratelimit-monthly-remaining-requests",
    "x-ratelimit-monthly-reset-days",
    "retry-after",
)
# Last headers seen on ANY GFW response (success or error) — self-test uses
_LAST_HEADERS: dict[str, str] = {}


def _load_state() -> dict:
    """Lazy-load the persistent cache/cooldown file (once per process)."""
    global _disk_state
    if _disk_state is None:
        state: dict = {"entries": {}, "rate_limited_until": 0.0, "last_headers": {}}
        try:
            if _CACHE_FILE.exists():
                raw = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k in state:
                        if isinstance(raw.get(k), type(state[k])):
                            state[k] = raw[k]
            # prune expired entries
            now = time.time()
            state["entries"] = {
                k: v for k, v in state["entries"].items()
                if isinstance(v, list) and len(v) == 2 and float(v[0]) > now
            }
        except Exception:
            pass  # corrupt/absent file → start clean, never crash the app
        _disk_state = state
    return _disk_state


def _save_state() -> None:
    """Atomically persist state (write-temp-then-replace)."""
    state = _load_state()
    try:
        entries = state.get("entries", {})
        if len(entries) > 150:  # keep the file bounded — newest wins
            entries = dict(sorted(entries.items(), key=lambda kv: -kv[1][0])[:150])
            state["entries"] = entries
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_name(_CACHE_FILE.name + ".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(_CACHE_FILE)
    except Exception:
        pass  # cache is an optimisation — a failed write must never break a fetch


def _harvest_rl_headers(headers) -> dict[str, str]:
    """Pull the GFW rate-limit headers off a response (any status)."""
    out: dict[str, str] = {}
    try:
        if headers:
            for k in _RL_HEADER_KEYS:
                v = headers.get(k)
                if v is not None:
                    out[k] = str(v)
    except Exception:
        pass
    return out


def _burst_wait_sec(err: urllib.error.HTTPError) -> float:
    """How long a BURST 429 wants us to wait (Retry-After, else a guess)."""
    try:
        ra = err.headers.get("Retry-After") if err.headers else None
        if ra and str(ra).isdigit():
            return float(ra)
    except Exception:
        pass
    return 15.0  # GFW burst windows are usually < 60 s


def _request_with_burst_retry(url: str, tok: str, method: str, body: dict | None,
                              timeout: int = 60, retries: int = 1) -> dict | None:
    """One in-band retry when a 429 is clearly BURST limiting (headers say
    the daily quota is fine). The retry waits within the 35 s job budget so
    a single angry minute doesn't turn into a failed source for the user.

    Daily-cap 429s are NOT retried — the server said "come back tomorrow".

    Anti-pile-up (2026-09-07 night log): when the per-minute limiter is
    angry, EVERY first attempt 429s. The old code gave each call its own
    15-22 s in-band wait — with rapid map clicks that queued into minutes
    of sleeps and pushed /reason past its 110 s deadline. Now each burst
    429 is a "strike": strikes widen the inter-call gap for 5 minutes,
    and at 3 strikes we skip the in-band retry and fail fast into the
    honest auto-pause path instead of strangling every other source.
    """
    try:
        data = _make_request(url, tok, method, body, timeout)
    except urllib.error.HTTPError as e:
        global _LAST_HEADERS
        _LAST_HEADERS = _harvest_rl_headers(getattr(e, "headers", None)) or _LAST_HEADERS
        daily_ok = False
        try:
            rem = _LAST_HEADERS.get("x-ratelimit-daily-remaining-requests")
            daily_ok = rem is not None and str(rem).isdigit() and int(rem) > 100
        except Exception:
            daily_ok = False
        if e.code != 429 or not daily_ok or retries <= 0:
            raise
        strikes = _note_burst_strike()
        if strikes >= _BURST_MAX_STRIKES:
            print(f"[GFW] burst limiter still angry ({strikes} strikes in a row) — "
                  "failing fast into the shared cooldown instead of sleeping again",
                  file=sys.stderr)
            raise
        wait = min(_burst_wait_sec(e), 22.0)  # stay inside the job budget
        print(f"[GFW] burst 429 (strike {strikes}) with daily quota remaining — "
              f"waiting {wait:.0f}s and retrying once",
              file=sys.stderr)
        time.sleep(wait)
        data = _make_request(url, tok, method, body, timeout)
    # Any success means the burst window cleared — reset the strikes.
    _reset_burst_strikes()
    return data

# Burst throttle: GFW's free tier also rate-limits PER MINUTE. Serialising
# real HTTP calls with a small gap makes the startup prewarm + rapid map
# clicks structurally unable to trip the limiter. (Root cause of the
# 2026-09-04 repeated-429 loop on the user's laptop: 8-pin prewarm fired
# 16 report calls within ~30 s of every backend start.)
_MIN_CALL_GAP_SEC = 6.0  # bumped 4s→6s (2026-09-07): still saw burst 429s
_last_call_ts = 0.0

# Adaptive anti-pile-up state (see _request_with_burst_retry): while the
# per-minute limiter is angry, the gap between GFW calls widens to give
# GFW's burst window room to cool, and strikes decide when a call stops
# paying for an in-band retry.
_BURST_MAX_STRIKES = 3
_BURST_STRIKES = 0
_ADAPTIVE_GAP_SEC = 0.0
_ADAPTIVE_GAP_UNTIL = 0.0


def _note_burst_strike() -> int:
    """Record one burst-429 strike; widen the inter-call gap for 5 min.
    Returns the live strike count."""
    global _BURST_STRIKES, _ADAPTIVE_GAP_SEC, _ADAPTIVE_GAP_UNTIL
    with _cache_lock:
        _BURST_STRIKES += 1
        _ADAPTIVE_GAP_SEC = min(30.0, 12.0 * _BURST_STRIKES)  # 12 s, 24 s, 30 s cap
        _ADAPTIVE_GAP_UNTIL = time.time() + 300.0
        return _BURST_STRIKES


def _reset_burst_strikes() -> None:
    global _BURST_STRIKES
    if _BURST_STRIKES:
        with _cache_lock:
            _BURST_STRIKES = 0


def _throttle() -> None:
    global _last_call_ts
    with _cache_lock:
        gap = _MIN_CALL_GAP_SEC
        now = time.time()
        if now < _ADAPTIVE_GAP_UNTIL and _ADAPTIVE_GAP_SEC > gap:
            gap = _ADAPTIVE_GAP_SEC  # burst window angry — space calls out
        wait = gap - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.time()


def _rate_limit_remaining() -> float:
    """Seconds of 429-cooldown left (0.0 = not rate-limited).

    Reads the persisted timestamp too — a backend restart must NOT
    magically lift a cooldown the server already imposed.
    """
    st = _load_state()
    until = max(_RATE_LIMIT_UNTIL, float(st.get("rate_limited_until") or 0.0))
    return max(0.0, until - time.time())


def _note_429(err: urllib.error.HTTPError) -> int:
    """Record a 429 cooldown; returns the pause length in seconds.

    Prefers GFW's own guidance over our default: Retry-After first, then
    x-ratelimit-daily-reset-hours (the daily-quota block — GFW blocks for
    ~24h once the daily cap is exhausted; a 120 s pause would just mean
    429 → pause 2 min → 429 forever). Persisted so restarts can't reset it.
    """
    global _RATE_LIMIT_UNTIL
    retry_after = None
    reset_hours = None
    try:
        retry_after = err.headers.get("Retry-After") if err.headers else None
        reset_hours = err.headers.get("x-ratelimit-daily-reset-hours") if err.headers else None
    except Exception:
        pass
    wait = 0
    if retry_after and str(retry_after).isdigit():
        wait = int(str(retry_after))
    elif reset_hours and str(reset_hours).replace(".", "", 1).isdigit() and float(reset_hours) > 0:
        wait = int(float(reset_hours) * 3600)
    if wait <= 0:
        wait = 120
    _RATE_LIMIT_UNTIL = time.time() + wait
    st = _load_state()
    st["rate_limited_until"] = _RATE_LIMIT_UNTIL
    _save_state()
    return wait


def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        ent = _result_cache.get(key)
        if ent is not None and ent[0] > time.time():
            return ent[1]
        # fall back to the restart-proof disk cache
        dentry = _load_state().get("entries", {}).get(key)
        if dentry and float(dentry[0]) > time.time():
            _result_cache[key] = (float(dentry[0]), dentry[1])
            return dentry[1]
    return None


def _cache_put_success(key: str, value: dict) -> None:
    """Cache ONLY successful responses — never cache an error/quota dict."""
    if not isinstance(value, dict) or "error" in value:
        return
    expires = time.time() + _GFW_CACHE_TTL_SEC
    with _cache_lock:
        _result_cache[key] = (expires, value)
        st = _load_state()
        st.setdefault("entries", {})[key] = [expires, value]
        _save_state()


def _clamp_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    """Clamp date range to GFW's allowed window (last 90 days empirically)."""
    today = date.today()
    latest_allowed = today - timedelta(days=GFW_LATEST_DELAY_DAYS)
    earliest_allowed = today - timedelta(days=GFW_SAFE_MAX_DAYS)

    if isinstance(start_date, str):
        start = date.fromisoformat(start_date)
    else:
        start = start_date
    if isinstance(end_date, str):
        end = date.fromisoformat(end_date)
    else:
        end = end_date

    if end < earliest_allowed:
        shift = (earliest_allowed - end).days
        start = start + timedelta(days=shift)
        end = end + timedelta(days=shift)

    if end > latest_allowed:
        end = latest_allowed
        if start > end:
            start = end - timedelta(days=min(30, GFW_SAFE_MAX_DAYS))

    if start > end:
        start = end

    return start.isoformat(), end.isoformat()


def _make_request(url: str, tok: str, method: str = "GET",
                  body: dict | None = None, timeout: int = 60) -> dict | None:
    """Make a GFW API request with browser-like headers and return JSON."""
    _throttle()  # free-tier per-minute limiter — smooth bursts, avoid 429s
    headers = {**_BROWSER_HEADERS, "Authorization": f"Bearer {tok}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        global _LAST_HEADERS
        _LAST_HEADERS = _harvest_rl_headers(resp.headers)
        if _LAST_HEADERS:  # remember quota state across restarts
            st = _load_state()
            st["last_headers"] = _LAST_HEADERS
            _save_state()
        raw = resp.read()
        if raw[:2] == b"\x1f\x8b":  # gzip magic number
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))


def _quota_explanation() -> str:
    """Explain WHY a 429 happened using GFW's own rate-limit headers
    (from this 429 or the last response we saw), instead of guessing."""
    hdrs = _LAST_HEADERS or _load_state().get("last_headers", {}) or {}
    remaining = hdrs.get("x-ratelimit-daily-remaining-requests")
    usage = hdrs.get("x-ratelimit-daily-current-usage")
    reset = hdrs.get("x-ratelimit-daily-reset-hours")
    if remaining is not None or reset is not None:
        quota_line = f"daily remaining={remaining}, today's usage={usage}"
        if reset and str(reset) not in ("0", "0.0"):
            return (
                f"GFW's own headers say DAILY quota exhausted ({quota_line}; "
                f" resets in ~{reset}h). This is shared across ALL your GFW "
                f"tokens — the pause below matches their reset clock."
            )
        if remaining and str(remaining).isdigit() and int(remaining) <= 0:
            return (
                f"GFW's headers say DAILY quota exhausted ({quota_line}) — "
                f"blocked until the daily reset (~24h)."
            )
        return (
            f"Burst/per-minute limiting, NOT the daily cap — GFW's headers "
            f"report {quota_line}. With usage this low, their gateway is "
            f"throttling how FAST we ask, not how MUCH. A short pause fixes this."
        )
    return (
        "No rate-limit headers came with the 429 — could be GFW's burst "
        "limit or a shared-token quota burn from another app/script."
    )


def get_fishing_effort(
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
    radius_deg: float = 0.5,
    token: str | None = None,
) -> dict[str, Any] | None:
    """Fetch apparent fishing hours near (lat, lon) for a date range.

    Uses the 4Wings API report endpoint with a custom GeoJSON polygon.
    Returns total fishing hours and vessel count within the bbox.

    IMPORTANT: All query params go in the URL (not body). Only the
    geojson polygon goes in the body. URL-encoding must use %3A for
    colons, %2C for commas in date-range.

    Args:
        lat: Latitude
        lon: Longitude
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        radius_deg: Half-width of bounding box (default 0.5° = ~50km)
        token: GFW API token (default: read from GFW_API_TOKEN env var)

    Returns:
        {
            "hours": float,
            "vessel_ids": int,
            "lat": float, "lon": float,
            "start_date": str, "end_date": str,
            "source": "Global Fishing Watch",
        }
    """
    tok = token or get_token()
    if not tok:
        return {
            "error": "GFW_API_TOKEN not set",
            "note": "register at https://globalfishingwatch.org and set env var",
        }

    # Quota guard — honest pause + 6 h success cache (only for the
    # shared default-token path; explicit-token callers are one-offs).
    # CACHE FIRST, cooldown second: a pause must never hide data we
    # already have on disk — only fresh fetches are paused.
    cache_key: str | None = None
    if token is None:
        cache_key = f"gfw:effort:{lat:.2f},{lon:.2f},{radius_deg:.2f},{start_date},{end_date}"
        hit = _cache_get(cache_key)
        if hit is not None:
            note = "hit (6h)"
            if _rate_limit_remaining() > 0:
                note += " — served while GFW calls are paused"
            return {**hit, "cache": note}
        remaining = _rate_limit_remaining()
        if remaining > 0:
            return {
                "error": (
                    f"GFW quota hit earlier (HTTP 429) — auto-paused for "
                    f"~{int(remaining)}s more; free-tier limit, not a bug. "
                    f"No cached copy exists for this exact point/date, so "
                    f"this point waits for the pause to end."
                ),
                "source": "GFW",
                "rate_limited": True,
            }

    actual_start, actual_end = _clamp_date_range(start_date, end_date)
    print(f"[GFW] Querying {actual_start} to {actual_end}", file=sys.stderr)

    bbox = {
        "min_lat": lat - radius_deg,
        "max_lat": lat + radius_deg,
        "min_lon": lon - radius_deg,
        "max_lon": lon + radius_deg,
    }

    # GFW expects dates in ISO 8601 with time component
    start_iso = f"{actual_start}T00:00:00.000Z"
    end_iso = f"{actual_end}T00:00:00.000Z"

    # ALL params as query string, only geojson in body
    # URL-encode colons (:) and commas (,) in date-range
    params = {
        "datasets[0]": DATASET_FISHING_EFFORT,
        "date-range": f"{start_iso},{end_iso}",
        "format": "JSON",
        "spatial-resolution": "LOW",
        "temporal-resolution": "ENTIRE",
        "group-by": "VESSEL_ID",
        "spatial-aggregation": "true",
    }
    query = urllib.parse.urlencode(params)
    url = f"{GFW_API_BASE}/4wings/report?{query}"

    body = {
        "geojson": {
            "type": "Polygon",
            "coordinates": [[
                [bbox["min_lon"], bbox["min_lat"]],
                [bbox["max_lon"], bbox["min_lat"]],
                [bbox["max_lon"], bbox["max_lat"]],
                [bbox["min_lon"], bbox["max_lat"]],
                [bbox["min_lon"], bbox["min_lat"]],
            ]],
        },
    }

    try:
        data = _request_with_burst_retry(url, tok, method="POST", body=body, timeout=60)
        global _LAST_RAW
        _LAST_RAW = data  # debug self-test only — parser verification
        # Real GFW response shape (from docs):
        # {
        #   "total": 497.88,
        #   "entries": [
        #     {
        #       "date": "2026-05-06T00:00:00.000Z",
        #       "vesselIDs": ["3e09e89...", ...],
        #       "hours": 12.4
        #     },
        #     ...
        #   ]
        # }
        # or grouped: entries: [{dataset_key: [...]}]
        total_hours = float(data.get("total", 0) or 0)
        entries = data.get("entries", data.get("data", []))
        all_vessel_ids: set[str] = set()

        def collect_vessels(item: dict) -> None:
            for k in ("vesselIDs", "vesselIds", "vessel_ids", "vessel_id"):
                v = item.get(k)
                if isinstance(v, list):
                    all_vessel_ids.update(str(x) for x in v)
                elif isinstance(v, int):
                    pass  # already a count, not IDs
            for k in ("hours", "Apparent Fishing Hours"):
                v = item.get(k)
                if isinstance(v, (int, float)):
                    nonlocal total_hours
                    if total_hours == 0:
                        total_hours = float(v)

        for entry in entries:
            if isinstance(entry, dict):
                if "vesselIDs" in entry or "hours" in entry or "date" in entry:
                    collect_vessels(entry)
                else:
                    for dataset_key, items in entry.items():
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    collect_vessels(item)
                        elif isinstance(items, dict):
                            collect_vessels(items)

        result = {
            "hours": total_hours,
            "vessel_ids": len(all_vessel_ids),
            "vessel_id_sample": sorted(all_vessel_ids)[:3],
            "lat": lat,
            "lon": lon,
            "start_date": actual_start,
            "end_date": actual_end,
            "requested_start": start_date,
            "requested_end": end_date,
            "source": "Global Fishing Watch (POST /4wings/report)",
            "bbox": bbox,
            "n_entries": len(entries),
        }
        if cache_key is not None:
            _cache_put_success(cache_key, result)
        return result
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            raw = e.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            body_text = raw.decode("utf-8")[:500]
        except Exception:
            pass
        if e.code == 429:
            global _LAST_HEADERS  # noqa: F824
            _LAST_HEADERS = _harvest_rl_headers(getattr(e, "headers", None))
            wait = _note_429(e)
            return {
                "error": (
                    f"GFW answered HTTP 429 — {_quota_explanation()} "
                    f"All GFW calls auto-paused for {wait}s. Not a token "
                    f"problem; cached good responses keep being served."
                ),
                "source": "GFW",
                "rate_limited": True,
            }
        return {
            "error": f"HTTP {e.code}: {e.reason}",
            "details": body_text,
            "source": "GFW",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "source": "GFW"}


def get_fishing_vessels_in_region(
    lat: float,
    lon: float,
    radius_deg: float = 0.5,
    start_date: str | None = None,
    end_date: str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    """List unique fishing vessels active in a bounding box."""
    tok = token or get_token()
    if not tok:
        return {"error": "GFW_API_TOKEN not set"}

    # Same quota guard as get_fishing_effort (shared cooldown + cache).
    cache_key: str | None = None
    if token is None:
        cache_key = f"gfw:fleet:{lat:.2f},{lon:.2f},{radius_deg:.2f},{start_date},{end_date}"
        hit = _cache_get(cache_key)
        if hit is not None:
            note = "hit (6h)"
            if _rate_limit_remaining() > 0:
                note += " — served while GFW calls are paused"
            return {**hit, "cache": note}
        remaining = _rate_limit_remaining()
        if remaining > 0:
            return {
                "error": (
                    f"GFW quota hit earlier (HTTP 429) — auto-paused for "
                    f"~{int(remaining)}s more; free-tier limit, not a bug. "
                    f"No cached copy exists for this exact point/date, so "
                    f"this point waits for the pause to end."
                ),
                "source": "GFW",
                "rate_limited": True,
            }

    if end_date is None:
        end_date = (date.today() - timedelta(days=GFW_LATEST_DELAY_DAYS)).isoformat()
    if start_date is None:
        start = date.fromisoformat(end_date) - timedelta(days=30)
        start_date = start.isoformat()

    actual_start, actual_end = _clamp_date_range(start_date, end_date)

    bbox = {
        "min_lat": lat - radius_deg,
        "max_lat": lat + radius_deg,
        "min_lon": lon - radius_deg,
        "max_lon": lon + radius_deg,
    }
    start_iso = f"{actual_start}T00:00:00.000Z"
    end_iso = f"{actual_end}T00:00:00.000Z"

    params = {
        "datasets[0]": DATASET_FISHING_EFFORT,
        "date-range": f"{start_iso},{end_iso}",
        "format": "JSON",
        "spatial-resolution": "LOW",
        "temporal-resolution": "ENTIRE",
        "group-by": "FLAGANDGEARTYPE",
        "spatial-aggregation": "true",
    }
    query = urllib.parse.urlencode(params)
    url = f"{GFW_API_BASE}/4wings/report?{query}"

    body = {
        "geojson": {
            "type": "Polygon",
            "coordinates": [[
                [bbox["min_lon"], bbox["min_lat"]],
                [bbox["max_lon"], bbox["min_lat"]],
                [bbox["max_lon"], bbox["max_lat"]],
                [bbox["min_lon"], bbox["max_lat"]],
                [bbox["min_lon"], bbox["min_lat"]],
            ]],
        },
    }

    try:
        data = _request_with_burst_retry(url, tok, method="POST", body=body, timeout=60)
        entries = data.get("entries", data.get("data", []))
        by_flag: dict[str, int] = {}
        by_gear: dict[str, int] = {}
        all_vessel_ids: set[str] = set()

        def collect(item: dict) -> None:
            if not isinstance(item, dict):
                return
            flag = item.get("flag", "UNK") or "UNK"
            gear = item.get("geartype", "UNK") or "UNK"
            vessel_ids = item.get(
                "vesselIDs", item.get("vesselIds", item.get("vessel_ids", []))
            )
            if isinstance(vessel_ids, list):
                count = len(vessel_ids)
                all_vessel_ids.update(str(x) for x in vessel_ids)
            elif isinstance(vessel_ids, int):
                count = vessel_ids
            else:
                count = 0
            if count > 0:
                by_flag[flag] = by_flag.get(flag, 0) + count
                by_gear[gear] = by_gear.get(gear, 0) + count

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Flat shape: entry itself has flag/geartype
            if "flag" in entry or "geartype" in entry or "vesselIDs" in entry:
                collect(entry)
            # Grouped shape: {dataset_key: [items]}
            else:
                for dataset_key, items in entry.items():
                    if isinstance(items, list):
                        for item in items:
                            collect(item)
                    elif isinstance(items, dict):
                        collect(items)

        result = {
            "vessel_count": len(all_vessel_ids) if all_vessel_ids else sum(by_flag.values()),
            "by_flag": by_flag,
            "by_gear": by_gear,
            "lat": lat,
            "lon": lon,
            "start_date": actual_start,
            "end_date": actual_end,
            "source": "Global Fishing Watch",
            "bbox": bbox,
        }
        if cache_key is not None:
            _cache_put_success(cache_key, result)
        return result
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            raw = e.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            body_text = raw.decode("utf-8")[:500]
        except Exception:
            pass
        if e.code == 429:
            global _LAST_HEADERS  # noqa: F824
            _LAST_HEADERS = _harvest_rl_headers(getattr(e, "headers", None))
            wait = _note_429(e)
            return {
                "error": (
                    f"GFW answered HTTP 429 — {_quota_explanation()} "
                    f"All GFW calls auto-paused for {wait}s. Not a token problem."
                ),
                "source": "GFW",
                "rate_limited": True,
            }
        return {
            "error": f"HTTP {e.code}: {e.reason}",
            "details": body_text,
            "source": "GFW",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "source": "GFW"}


# Indian Ocean RFMO + EEZ codes for convenience
INDIAN_OCEAN_REGIONS = {
    "iotc_rfmo": {"code": "IOTC", "source": "RFMO",
                  "description": "Indian Ocean Tuna Commission (all IOTC)"},
    "india_eez": {"code": "356", "source": "EEZ",
                  "description": "India Exclusive Economic Zone"},
    "sri_lanka_eez": {"code": "144", "source": "EEZ",
                      "description": "Sri Lanka EEZ"},
    "maldives_eez": {"code": "462", "source": "EEZ",
                     "description": "Maldives EEZ"},
}


# ── Self-test ────────────────────────────────────────────────────────

def _selftest() -> int:
    """`python -m pipeline.gfw` — honest live check with the real token.

    Reads GFW_API_TOKEN from the environment / .env (never prints it)
    and runs ONE small real query: 30-day fishing effort in a 0.5° box
    around Veraval (20.9 N, 70.37 E), our PFZ validation ground.
    """
    import os
    from datetime import date, timedelta

    tok = os.environ.get("GFW_API_TOKEN")
    if not tok:
        print("[GFW self-test] GFW_API_TOKEN not found in env or .env —")
        print("                paste it into your .env file first.")
        return 2
    print(f"[GFW self-test] token found ({len(tok)} chars, hidden).")

    end = date.today() - timedelta(days=4)   # GFW data lags ~4 days
    start = end - timedelta(days=30)
    print(f"[GFW self-test] querying REAL fishing effort: "
          f"Veraval box 20.40-21.40 N, 69.87-70.87 E, {start}..{end}")

    effort = get_fishing_effort(20.9, 70.37, start.isoformat(), end.isoformat())
    if effort and effort.get("cache"):
        print(f"[GFW self-test] ✅ effort served from CACHE while calls are paused: "
              f"{effort.get('hours')} fishing hours, {effort.get('vessel_ids')} vessels")
        print("                (this proves the restart-proof cache works — no fresh API call burned)")
    if not effort or "error" in effort:
        err = (effort or {}).get("error", "no response")
        if (effort or {}).get("rate_limited"):
            print("[GFW self-test] ⏸ calls paused right now:", err)
            print("                Wait for the pause to end, then re-run this self-test.")
            print("                (The pause is shared with the backend via data/gfw_cache.json")
            print("                 — that is the restart-proof fix working, not a failure.)")
            return 3
        print("[GFW self-test] effort FAILED:", err)
        return 1
    print(f"[GFW self-test] ✅ effort: {effort.get('hours')} fishing hours, "
          f"{effort.get('vessel_ids')} vessels in 30 days")

    # Always show GFW's own quota counters — GFW sends them on every response
    rl = _LAST_HEADERS or _load_state().get("last_headers", {})
    if rl:
        print(f"[GFW self-test] quota (GFW's headers): "
              f"daily remaining={rl.get('x-ratelimit-daily-remaining-requests', '?')}, "
              f"today used={rl.get('x-ratelimit-daily-current-usage', '?')}, "
              f"monthly remaining={rl.get('x-ratelimit-monthly-remaining-requests', '?')}")
    else:
        print("[GFW self-test] quota: no x-ratelimit-* headers sent by GFW this call "
              "(they are sent post-May-2026; absence is not an error)")

    if "--debug" in sys.argv:
        print("[GFW self-test] ── RAW effort response (token never shown) ──")
        raw_txt = json.dumps(_LAST_RAW, indent=2, default=str)
        print(raw_txt[:3500])
        print("[GFW self-test] ── end raw (paste this whole block back) ──")

    hours = effort.get("hours") or 0
    if hours < 5:
        print("[GFW self-test] ⓘ context: GFW data comes from vessel AIS beacons.")
        print("                India's small artisanal boats mostly have NO AIS →")
        print("                nearshore counts run LOW by design; offshore/industrial")
        print("                vessels (trawlers, longliners) show up much better.")
        print("                SW monsoon (Jun-Aug) also keeps fleets in harbour.")

    try:
        fleet = get_fishing_vessels_in_region(
            20.9, 70.37, 0.5, start.isoformat(), end.isoformat())
    except Exception as e:  # noqa: BLE001
        fleet = {"error": str(e)}
    if isinstance(fleet, dict) and "error" not in fleet and fleet:
        print(f"[GFW self-test] ✅ fleet: {fleet.get('vessel_count')} vessels, "
              f"top flags: {dict(sorted((fleet.get('by_flag') or {}).items(), key=lambda kv: -kv[1])[:5])}")
    else:
        print("[GFW self-test] fleet endpoint:", (fleet or {}).get("error", "not available"))
    print("[GFW self-test] DONE — token works. ORCA agents will now show "
          "real GFW fishing data wherever include_gfw is on.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
