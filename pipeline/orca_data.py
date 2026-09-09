"""ORCA unified data layer — one function, five data sources.

This module is the single entry point for the rest of the backend and
the Next.js frontend. It hides the multi-source plumbing and returns a
clean, normalized dict per lat/lon (a "ZoneSnapshot").

The five data sources (in priority order):

    1. NOAA ERDDAP DINEOF chlorophyll  (FREE, no key)  → chlorophyll
    2. Open-Meteo Marine API            (FREE, no key)  → SST + waves
    3. Global Fishing Watch AIS         (FREE w/ token) → fishing activity
    4. INCOIS LAS OPeNDAP               (FREE, no key)  → backup chlorophyll
    5. MOSDAC OCM-3 L4 (local)          (🇮🇳 creds)     → primary chlorophyll

Each source is fetched in turn with a try/except — if one fails (network,
auth, quota), the snapshot still has data from the others. Sources are
not fatal; the snapshot is always returned, possibly with `error` keys
and `data_sources_used` listing what succeeded.

Usage:

    from pipeline.orca_data import zone_snapshot, grid_snapshot

    snap = zone_snapshot(19.0, 72.8, "2026-08-15")
    # Returns:
    # {
    #   "lat": 19.0, "lon": 72.8, "date": "2026-08-15",
    #   "sst_max": 29.6, "sst_min": 28.3, "wave_max": 2.86,
    #   "chlorophyll": 0.42,        # mg/m^3
    #   "fishing_hours": 1.0,        # hours in 30 days
    #   "vessel_count": 3,
    #   "fleet_by_flag": {"IND": 3},
    #   "fleet_by_gear": {"trawlers": 1, "pole_and_line": 1, "inconclusive": 1},
    #   "data_sources_used": ["NOAA ERDDAP", "Open-Meteo", "GFW AIS", "INCOIS"],
    #   "data_sources_failed": [],
    #   "fetched_at": "2026-09-02T19:50:00Z",
    # }
"""
from __future__ import annotations

import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import date, datetime, timedelta, timezone
from typing import Any

from pipeline.openmeteo_sst import get_sst_at_point

# Per-source timeout. If a source takes longer than this, we move on
# without it. The full snapshot completes in ~sum-of-timeouts in the
# worst case, but in practice with the thread pool all sources run
# concurrently and the total is bounded by max timeout.
# Per-source cap inside the PARALLEL gather. 20 s (was 12): the US-hosted
# chlorophyll servers (NOAA/OC-CCI) regularly need 12-20 s from Indian
# networks — the old cap killed them before they could answer. Parallel
# gather means the wall-clock is max(source times), not the sum, so a
# bigger cap costs nothing when others are fast.
SOURCE_TIMEOUT_SEC = 20.0

# Lazy source getters. They import the heavy modules (which may need
# numpy/xarray) on first call, and they look up the function via the
# module attribute each time — so tests can monkey-patch
# `pipeline.erddap_chl.get_chlorophyll_with_fallback` and the change
# takes effect.
def _get_noaa():
    from pipeline import erddap_chl
    return erddap_chl.get_chlorophyll_with_fallback

def _get_incois():
    from pipeline import incois
    return incois.get_chlorophyll

def _get_occci():
    from pipeline import occci_chl
    return occci_chl.get_chlorophyll

def _get_mosdac_or_none():
    """ISRO MOSDAC live getter — None when disabled/creds absent, so the
    source simply doesn't enter the gather (AUTO pattern like GFW)."""
    from pipeline import mosdac_ocm
    if not mosdac_ocm.mosdac_enabled():
        return None
    return mosdac_ocm.get_chlorophyll

def _get_gfw_effort():
    from pipeline import gfw
    return gfw.get_fishing_effort

def _get_gfw_fleet():
    from pipeline import gfw
    return gfw.get_fishing_vessels_in_region

def _get_baseline():
    """Anomaly agent's cached ERA5 baseline walker. The snapshot warms
    it INSIDE the parallel gather so the 10-agent run never pays the
    3 archive calls serially afterwards (that serial tail pushed a cold
    /reason past its 110 s deadline on the 2026-09-07 night log)."""
    from pipeline.agents import anomaly
    return anomaly.baseline_cached

def _get_wx_summary():
    """Weather agent's cached daily summary — same ttlcache key the
    weather agent and the advisory read, so warming = instant 'hit'."""
    from pipeline.agents import weather
    return weather.get_daily_summary


# Default date window for time-windowed sources (fishing, chlorophyll history)
DEFAULT_WINDOW_DAYS = 30

# Bounding-box radius (deg) for fishing vessel queries
DEFAULT_RADIUS_DEG = 0.5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe(callable_, *args, default=None, label="source", timeout: float = SOURCE_TIMEOUT_SEC, **kwargs) -> tuple[Any, str | None]:
    """Run a data source, return (result, error_message). Never raises.

    If the source doesn't return within `timeout` seconds, returns a
    timeout error instead of hanging the whole snapshot.
    """
    def _call():
        result = callable_(*args, **kwargs)
        if isinstance(result, dict) and "error" in result and len(result) == 2:
            return None, f"{label}: {result['error']}"
        return result, None

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call)
            try:
                return future.result(timeout=timeout)
            except FuturesTimeout:
                return None, f"{label}: timeout after {timeout:.0f}s"
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc(limit=2)
        return None, f"{label}: {type(e).__name__}: {e}\n{tb}"


def _gather(
    jobs: dict[str, tuple],
    timeout: float = SOURCE_TIMEOUT_SEC,
) -> dict[str, tuple[Any, str | None]]:
    """Run named source jobs CONCURRENTLY, same (result, error) convention
    as _safe(). Wall-clock ≈ slowest single source instead of the sum —
    this is what saves a cold snapshot from blowing through the Next.js
    dev-proxy socket (seen on Windows: ~85 s sequential → ECONNRESET)."""
    out: dict[str, tuple[Any, str | None]] = {}
    if not jobs:
        return out
    ex = ThreadPoolExecutor(max_workers=len(jobs))
    futs = {name: ex.submit(j[0], *j[1], **j[2]) for name, j in jobs.items()}
    for name, fut in futs.items():
        label = jobs[name][3]
        to = jobs[name][4] if len(jobs[name]) > 4 else timeout  # per-job override
        try:
            res = fut.result(timeout=to)
            if isinstance(res, dict) and "error" in res and len(res) == 2:
                out[name] = (None, f"{label}: {res['error']}")
            else:
                out[name] = (res, None)
        except FuturesTimeout:
            out[name] = (None, f"{label}: timeout after {to:.0f}s")
        except Exception as e:  # noqa: BLE001
            out[name] = (None, f"{label}: {type(e).__name__}: {e}")
    ex.shutdown(wait=False, cancel_futures=True)
    return out


def zone_snapshot(
    lat: float,
    lon: float,
    target_date: str | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    radius_deg: float = DEFAULT_RADIUS_DEG,
    include_gfw: bool = True,
    warm_extras: bool = True,
) -> dict[str, Any]:
    """Build a unified ZoneSnapshot for a single lat/lon.

    Fetches from NOAA, Open-Meteo, GFW (optional), and INCOIS, with all
    sources running CONCURRENTLY. Each source failure is non-fatal; the
    snapshot is always returned.

    Args:
        lat, lon: Center of the zone (decimal degrees).
        target_date: Date string (YYYY-MM-DD) for the snapshot. Default: today.
        window_days: Look-back window for time-aggregated sources (fishing,
            chlorophyll history).
        radius_deg: Bounding-box half-width for the GFW query.
        include_gfw: If False, skip the GFW call (useful for unit tests and
            for callers without a GFW token).
        warm_extras: If True (single-point interactive clicks), the gather
            also warms the shared agent caches (ERA5 baseline, today's
            weather, NOAA 3-day-lag chlorophyll) so reason()/advisory()
            pay no serial network afterwards. Grid cells pass False so a
            25-cell sweep doesn't multiply archive/ERDDAP load.

    Returns:
        Dict with normalized fields (see module docstring).
    """
    if target_date is None:
        target_date = date.today().isoformat()

    # Compute windowed dates for GFW (last N days ending ~4 days ago — GFW lag)
    end = date.fromisoformat(target_date)
    gfw_end = (end - timedelta(days=4)).isoformat()
    gfw_start = (date.fromisoformat(gfw_end) - timedelta(days=window_days)).isoformat()
    # NOAA/INCOIS use a recent date as the file index — use target_date as-is
    chl_date = target_date
    # VIIRS chlorophyll runs on a ~3-day processing lag, so the ~3-day-old
    # analysis file is what actually exists most days. Warmed UPFRONT in
    # the parallel gather (not a serial second fetch after "today" comes
    # back empty) — the fallback then costs zero wall-clock.
    prev_chl_date = (date.fromisoformat(target_date) - timedelta(days=3)).isoformat()
    prev7_chl_date = (date.fromisoformat(target_date) - timedelta(days=7)).isoformat()

    snap: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
        "date": target_date,
        "fetched_at": _now_iso(),
        "data_sources_used": [],
        "data_sources_failed": [],
    }

    # ── Sources 1–3 run CONCURRENTLY (Open-Meteo + NOAA + OC-CCI + INCOIS).
    # Sequential fetching cost ~85 s in the worst case, and the UI fires
    # /reason + /advisory for the same point at the same moment — parallel
    # fetching plus single-flight caching (ttlcache) is what keeps the
    # Next.js dev proxy from resetting the connection on slow networks.
    noaa_fn = occci_fn = None
    try:
        noaa_fn = _get_noaa()
    except ImportError as e:
        snap["data_sources_failed"].append(f"NOAA: import error: {e}")
    try:
        occci_fn = _get_occci()
    except ImportError as e:
        snap["data_sources_failed"].append(f"OC-CCI: import error: {e}")
    mosdac_fn = None
    try:
        mosdac_fn = _get_mosdac_or_none()
    except ImportError as e:
        snap["data_sources_failed"].append(f"MOSDAC OCM-3: import error: {e}")

    jobs: dict[str, tuple] = {
        "openmeteo": (get_sst_at_point, (lat, lon, gfw_start, gfw_end), {}, "Open-Meteo"),
    }
    if noaa_fn is not None:
        jobs["noaa"] = (noaa_fn, (lat, lon, chl_date), {}, "NOAA ERDDAP")
    if occci_fn is not None:
        jobs["occci"] = (occci_fn, (lat, lon, chl_date), {}, "ESA OC-CCI", 25.0)  # slow shared server
    if mosdac_fn is not None:
        # ISRO live chain (login + search + granule download + extract).
        # The chain paces ITSELF at JOB_BUDGET_SEC (75 s, stage-guarded)
        # and always returns a stage-precise error; this outer cap is
        # 9 s LOOSER so the gather never namelessly decapitates the
        # chain milliseconds before it could speak (the bare "timeout
        # after 75s" card the user saw even AFTER the stage-guard fix —
        # chain budget == gather cap was an exact-tie race).
        jobs["mosdac"] = (mosdac_fn, (lat, lon, chl_date), {}, "ISRO MOSDAC OCM-3", 84.0)

    if warm_extras:
        if noaa_fn is not None:
            # Upfront 3-day-lag VIIRS analysis (see note by prev_chl_date).
            jobs["noaa_prev"] = (
                noaa_fn, (lat, lon, prev_chl_date), {}, "NOAA ERDDAP (3-day-lag analysis)",
            )
        # Silent warmers: results are NOT snapshot fields — they pre-fill
        # the shared ttlcache under the exact keys the anomaly/weather
        # agents (and the advisory) read, so the serial 10-agent run that
        # follows the gather finds them warm. Never listed as
        # used/failed sources: the agents report their own status.
        try:
            jobs["climo"] = (_get_baseline(), (lat, lon, target_date), {}, "ERA5 baseline", 28.0)
        except ImportError:
            pass
        try:
            jobs["wx_now"] = (_get_wx_summary(), (lat, lon, target_date), {}, "Open-Meteo weather", 14.0)
        except ImportError:
            pass

    # GFW runs INSIDE the same parallel gather (they're slow paid-report
    # POSTs — 35 s budget each) instead of a serial block after it.
    # Sequential GFW cost ~70 s extra on the user's network and pushed
    # every cold /reason past the route deadline → endless 504s.
    if include_gfw:
        try:
            jobs["gfw_effort"] = (
                _get_gfw_effort(), (lat, lon, gfw_start, gfw_end, radius_deg),
                {}, "GFW fishing effort", 35.0,
            )
        except ImportError as e:
            snap["data_sources_failed"].append(f"GFW effort: import error: {e}")
        try:
            jobs["gfw_fleet"] = (
                _get_gfw_fleet(), (lat, lon, radius_deg, gfw_start, gfw_end),
                {}, "GFW fleet", 35.0,
            )
        except ImportError as e:
            snap["data_sources_failed"].append(f"GFW fleet: import error: {e}")

    results = _gather(jobs, timeout=SOURCE_TIMEOUT_SEC)

    # 1) Open-Meteo SST + waves
    sst, err = results.get("openmeteo", (None, "Open-Meteo: not run"))
    if sst and not err:
        snap["sst_max"] = sst.get("sst_max") if isinstance(sst, dict) else None
        snap["sst_min"] = sst.get("sst_min") if isinstance(sst, dict) else None
        snap["sst_mean"] = sst.get("sst_mean") if isinstance(sst, dict) else None
        snap["wave_max"] = sst.get("wave_max") if isinstance(sst, dict) else None
        snap["wave_mean"] = sst.get("wave_mean") if isinstance(sst, dict) else None
        snap["data_sources_used"].append("Open-Meteo Marine (SST + waves)")
    else:
        snap["data_sources_failed"].append(err or "Open-Meteo: no data")

    # 2) NOAA ERDDAP chlorophyll
    # VIIRS data runs on a ~3-day processing lag, so "today" (and usually
    # the last 2 days) have no files yet. Try the requested date first;
    # if it has nothing, step back 3 days and surface chlorophyll_date so
    # the caller/UI can show the data's true age. Never invent a value.
    chl, err_noaa = results.get("noaa", (None, None))
    got_noaa = bool(chl and not err_noaa and isinstance(chl, dict) and chl.get("value") is not None)
    attempt_date = chl_date
    if not got_noaa and noaa_fn is not None:
        attempt_date = prev_chl_date
        if "noaa_prev" in results:
            # Already fetched inside the parallel gather — free.
            chl2, err2 = results["noaa_prev"]
        else:
            # Grid/warm_extras=False path: conditional serial fallback,
            # so a 25-cell sweep stays polite with ERDDAP.
            chl2, err2 = _safe(
                noaa_fn, lat, lon, attempt_date,
                default=None, label="NOAA ERDDAP",
            )
        if chl2 and not err2 and isinstance(chl2, dict) and chl2.get("value") is not None:
            chl = chl2
            got_noaa = True
        else:
            # ONE clean bullet, not two confusing ones: when both the
            # requested date AND the lag analysis failed, say so once.
            # 3rd chance: VIIRS processing kabhi 3 din se zyada peeche
            # hota hai — 7-day-lag bhi try (sirf isi rare fail-path pe).
            chl3, err3 = _safe(
                noaa_fn, lat, lon, prev7_chl_date,
                default=None, label="NOAA ERDDAP (7-day lag)",
            )
            if (chl3 and not err3 and isinstance(chl3, dict)
                    and chl3.get("value") is not None):
                chl = chl3
                got_noaa = True
                attempt_date = prev7_chl_date
            elif err2 and err_noaa:
                err_noaa = (
                    "NOAA ERDDAP (today, 3-day & 7-day lag tried): "
                    + str(err3 or err2).split(": ", 1)[-1]
                )
            else:
                err_noaa = err3 or err2 or err_noaa or "NOAA: no data"

    if got_noaa and isinstance(chl, dict):
        snap["chlorophyll"] = chl.get("value")
        snap["chlorophyll_unit"] = chl.get("units", "mg/m^3")
        snap["chlorophyll_source"] = chl.get("source", "NOAA ERDDAP DINEOF")
        snap["chlorophyll_date"] = attempt_date
        if attempt_date != chl_date:
            snap["chlorophyll_note"] = (
                f"Requested date had no product yet (satellite lag); "
                f"showing {attempt_date} analysis instead."
            )
        if chl.get("box_min") is not None:
            snap["chlorophyll_box_min"] = chl["box_min"]
            snap["chlorophyll_box_max"] = chl["box_max"]
        snap["data_sources_used"].append(f"NOAA ERDDAP (chlorophyll, {attempt_date})")
    elif noaa_fn is not None:
        snap["data_sources_failed"].append(err_noaa or "NOAA: no data")

    # 2b) ESA OC-CCI cross-validation — and SECOND fallback: when NOAA
    # has nothing but OC-CCI does, promote it to the primary chlorophyll
    # (honest, independent dataset) before resorting to INCOIS.
    if occci_fn is not None:
        occci, err = results.get("occci", (None, "ESA OC-CCI: not run"))
        if occci and not err and occci.get("value") is not None:
            snap["chlorophyll_occci"] = occci.get("value")
            snap["chlorophyll_occci_source"] = occci.get("source", "ESA OC-CCI")
            if "chlorophyll" not in snap:
                snap["chlorophyll"] = occci.get("value")
                snap["chlorophyll_unit"] = occci.get("units", "mg/m^3")
                snap["chlorophyll_source"] = occci.get("source", "ESA OC-CCI")
                snap["chlorophyll_date"] = occci.get("date")
                snap["chlorophyll_note"] = "NOAA unavailable; showing ESA OC-CCI latest-analysis instead."
                snap["data_sources_used"].append("ESA OC-CCI (chlorophyll, fallback primary)")
            else:
                snap["data_sources_used"].append("ESA OC-CCI (chlorophyll cross-check)")
        else:
            snap["data_sources_failed"].append(
                err or (occci or {}).get("error") or "OC-CCI: no data"
            )

    # 2c) ISRO MOSDAC OCM-3 live — desi third source. Cross-check role
    # like OC-CCI; never masks NOAA as primary, but its presence lets the
    # satellite agent do a NOAA vs ESA vs ISRO three-way comparison. 🇮🇳
    if mosdac_fn is not None:
        mosdac, merr = results.get("mosdac", (None, "MOSDAC OCM-3: not run"))
        if mosdac and not merr and mosdac.get("value") is not None:
            snap["chlorophyll_mosdac"] = mosdac.get("value")
            snap["chlorophyll_mosdac_source"] = mosdac.get("source", "ISRO MOSDAC")
            snap["chlorophyll_mosdac_date"] = mosdac.get("date")
            if mosdac.get("note"):
                snap["chlorophyll_mosdac_note"] = mosdac["note"]
            # pixel forensics for the satellite agent's skepticism tiers
            for k in ("pixel_km", "ring_valid", "ring_median",
                      "area_median", "area_valid", "cdom_value", "cdom_units"):
                if mosdac.get(k) is not None:
                    snap[f"chlorophyll_mosdac_{k}"] = mosdac[k]
            snap["data_sources_used"].append("ISRO MOSDAC OCM-3 (chlorophyll, live 🇮🇳)")
        else:
            snap["data_sources_failed"].append(
                merr or (mosdac or {}).get("error") or "MOSDAC OCM-3: no data"
            )

    # 3) INCOIS backup chlorophyll — CONDITIONAL: only queried when both
    # NOAA and OC-CCI failed, so the flaky server never sits in the hot
    # path (and never shows as "failed" noise when it wasn't even used).
    # Since 2026-09-04 the query itself is crash-safe (server-side
    # hyperslab subset, KBs on the wire — the GBs-into-RAM path is gone).
    if "chlorophyll" not in snap:
        try:
            incois_fn = _get_incois()
        except ImportError as e:
            incois_fn = None
            incois_imp_err = e
        if incois_fn is not None:
            incois_chl, err = _safe(
                incois_fn, lat, lon, chl_date,
                default=None, label="INCOIS LAS", timeout=30,
            )
            if incois_chl and not err and incois_chl.get("value") is not None:
                snap["chlorophyll"] = incois_chl.get("value")
                snap["chlorophyll_unit"] = incois_chl.get("units", "mg/m^3")
                snap["chlorophyll_source"] = incois_chl.get("source", "INCOIS LAS")
                snap["chlorophyll_date"] = chl_date
                if incois_chl.get("note"):
                    snap["chlorophyll_note"] = incois_chl["note"]
                snap["data_sources_used"].append("INCOIS LAS (backup chlorophyll)")
            else:
                snap["data_sources_failed"].append(
                    err or (incois_chl or {}).get("error") or "INCOIS: no data"
                )
        else:
            snap["data_sources_failed"].append(f"INCOIS: import error: {incois_imp_err}")

    # 4) GFW fishing effort + fleet composition (fetched in the parallel
    # gather above — just map the results here)
    if include_gfw:
        effort, err = results.get("gfw_effort", (None, "GFW effort: not run"))
        if effort and not err and "error" in effort:
            err = f"GFW effort: {effort['error']}"  # token invalid/expired/quota — surface honestly
            effort = None
        if effort and not err:
            hours = effort.get("hours")
            if hours is not None:
                snap["fishing_hours"] = hours
                snap["vessel_count_effort"] = effort.get("vessel_ids", 0)
                snap["data_sources_used"].append("Global Fishing Watch (effort)")
            else:
                snap["data_sources_failed"].append(
                    "GFW effort: response has no 'hours' field"
                )
        else:
            snap["data_sources_failed"].append(err or "GFW effort: no data")

        fleet, err = results.get("gfw_fleet", (None, "GFW fleet: not run"))
        if fleet and not err and "error" in fleet:
            err = f"GFW fleet: {fleet['error']}"
            fleet = None
        if fleet and not err and "by_flag" in fleet:
            snap["vessel_count"] = fleet.get("vessel_count")
            snap["fleet_by_flag"] = fleet.get("by_flag", {})
            snap["fleet_by_gear"] = fleet.get("by_gear", {})
            snap["data_sources_used"].append("Global Fishing Watch (fleet)")
        else:
            snap["data_sources_failed"].append(err or "GFW fleet: no data")
    else:
        snap["data_sources_failed"].append("GFW: skipped (include_gfw=False)")

    # 5) Near-term wave context (NOW + next-48h peak) from the point
    # forecast. The snapshot's historical wave_max is the max over the
    # PAST ~30-day window — labelling it as "today's risk" made the
    # reason panel look contradictory next to the advisory card's
    # current readings. Forecast fetch is cheap (30-min cached per cell).
    try:
        from pipeline import forecast as fc
        pf = fc.get_point_forecast(lat, lon)
        now_blk = pf.get("now") or {}
        n48_blk = pf.get("next48h") or {}
        if now_blk.get("wave_height_m") is not None:
            snap["wave_now_m"] = now_blk["wave_height_m"]
        if n48_blk.get("wave_max_m") is not None:
            snap["wave_peak_48h_m"] = n48_blk["wave_max_m"]
    except Exception:  # noqa: BLE001
        pass  # ocean agent falls back to the labelled 30-day window max

    # 6) Simple PFZ heuristic score (chlorophyll + SST + fishing presence)
    snap["pfz_score"] = _pfz_score(snap)

    return snap


def _pfz_score(snap: dict[str, Any]) -> float | None:
    """Naive PFZ score 0-1: high chlorophyll, optimal SST, fishing presence.

    For real PFZ we'd use INCOIS's actual algorithm. This is a stopgap
    so the UI can highlight zones in the meantime.
    """
    score = 0.0
    weights = 0.0

    # Chlorophyll: 0.1 (low) to 10+ (very high) mg/m^3 — bell curve, peak at 1-3
    chl = snap.get("chlorophyll")
    if chl is not None and chl > 0:
        # log scale, peak at 1.0
        import math
        score += 1.0 - abs(math.log10(chl)) * 0.4
        weights += 1.0

    # SST: tuna and pelagics prefer 24-29°C
    sst = snap.get("sst_mean") or snap.get("sst_max")
    if sst is not None:
        if 24 <= sst <= 29:
            score += 1.0
        elif 22 <= sst <= 31:
            score += 0.5
        else:
            score += 0.0
        weights += 1.0

    # Fishing presence: any boats = +0.3
    if (snap.get("fishing_hours") or 0) > 0:
        score += 0.3
        weights += 0.3

    if weights == 0:
        return None
    return round(min(1.0, max(0.0, score / weights)), 2)


def zone_snapshot_cached(
    lat: float,
    lon: float,
    target_date: str | None = None,
    radius_deg: float = DEFAULT_RADIUS_DEG,
    include_gfw: bool = True,
    ttl_sec: float = 600.0,
    warm_extras: bool = True,
) -> dict[str, Any]:
    """zone_snapshot with a 10-minute cache per 0.05° cell.

    The advisory card, chat trace and reason endpoint all need the same
    snapshot; without a cache each of them paid the full ~60–90 s
    multi-source fetch. Cached, the second caller gets an instant answer
    (which is what makes the 30-second demo flow possible). Cached
    values are immutable-by-convention — callers must not mutate.

    warm_extras is intentionally NOT part of the cache key: the extra
    jobs only pre-fill shared agent caches and replace an identical
    serial fallback — the snapshot content is the same either way.
    """
    from pipeline.ttlcache import cached
    # Normalize: None and "today" must map to the SAME cache key or
    # the advisory (passes None) and the chat trace (passes today's
    # string) would each pay a separate 60–90 s fetch for identical data.
    if target_date is None:
        target_date = date.today().isoformat()
    key = f"snapshot:{lat:.2f}:{lon:.2f}:{target_date}:{include_gfw}:{radius_deg}"
    return cached(key, ttl_sec, lambda: zone_snapshot(
        lat, lon, target_date, radius_deg=radius_deg, include_gfw=include_gfw,
        warm_extras=warm_extras,
    ))


def grid_snapshot(
    min_lat: float, max_lat: float, min_lon: float, max_lon: float,
    target_date: str | None = None,
    step_deg: float = 1.0,
    include_gfw: bool = False,  # off by default for grids (GFW is per-cell)
) -> dict[str, Any]:
    """Build snapshots on a regular grid.

    GFW is disabled by default for grids because it's expensive
    (one call per cell). Pass include_gfw=True only for small grids.

    Returns:
        {"min_lat", "max_lat", "min_lon", "max_lon", "step_deg",
         "n_points", "points": [<ZoneSnapshot>...]}
    """
    if target_date is None:
        target_date = date.today().isoformat()

    lats, lons = [], []
    lat = min_lat
    while lat <= max_lat + 1e-9:
        lats.append(round(lat, 4))
        lat += step_deg
    lon = min_lon
    while lon <= max_lon + 1e-9:
        lons.append(round(lon, 4))
        lon += step_deg

    n_pts = len(lats) * len(lons)
    print(
        f"[ORCA] Grid {len(lats)}×{len(lons)} = {n_pts} points, "
        f"{min_lat}..{max_lat}, {min_lon}..{max_lon}, date={target_date}",
        file=sys.stderr,
    )

    points = []
    for la in lats:
        for lo in lons:
            snap = zone_snapshot_cached(
                la, lo, target_date,
                radius_deg=step_deg,
                include_gfw=include_gfw,
                warm_extras=False,  # grid sweep: don't multiply archive/ERDDAP load
            )
            points.append(snap)

    return {
        "min_lat": min_lat, "max_lat": max_lat,
        "min_lon": min_lon, "max_lon": max_lon,
        "step_deg": step_deg,
        "date": target_date,
        "fetched_at": _now_iso(),
        "n_points": len(points),
        "points": points,
    }


# Real coordinates for 8 Indian coastal zones. NOT dummy data — these
# are real lat/lon points that trigger real API calls. They're just a
# UI convenience for the SIH pitch; any lat/lon works.
INDIAN_COASTAL_ZONES = [
    {"name": "Mumbai offshore",      "lat": 19.0, "lon": 72.8},
    {"name": "Goa offshore",         "lat": 15.5, "lon": 73.7},
    {"name": "Cochin offshore",      "lat":  9.5, "lon": 76.0},
    {"name": "Chennai offshore",     "lat": 13.5, "lon": 80.5},
    {"name": "Visakhapatnam",        "lat": 17.5, "lon": 83.5},
    {"name": "Kandla/Gujarat",       "lat": 22.5, "lon": 68.5},
    {"name": "Andaman (Port Blair)", "lat": 12.0, "lon": 92.5},
    {"name": "Lakshadweep",          "lat": 10.5, "lon": 72.5},
]

# Keep DEMO_ZONES as an alias for backwards compatibility — but the
# canonical name is INDIAN_COASTAL_ZONES.
DEMO_ZONES = INDIAN_COASTAL_ZONES
