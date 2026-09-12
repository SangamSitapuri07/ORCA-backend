"""Agent 8: Anomaly Detection 🔍

Computes a provisional SST deviation from a small Open-Meteo Archive sample:
the same date plus two days in each of the three prior years (or fewer when a
request fails). This is not a 30-year climatology, z-score, IPCC attribution,
or marine-heatwave diagnosis. The 1/2/3°C bands are internal ORCA display
flags requiring scientific validation.

Inputs: ZoneSnapshot (lat, lon, target_date)
Outputs: dict of findings
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SOURCE_LABEL = "Open-Meteo Archive (three-prior-year date-window sample)"


def _fetch_baseline(lat: float, lon: float, target_date: str, window_years: int = 3) -> dict:
    """Fetch the same date-of-year from the past N years to build a baseline.

    Uses at most the last 3 years as a small comparison sample, not climatology.
    Time-budgeted: on slow networks each ERA5 archive call can eat
    15-40 s, so we hard-stop at ~22 s total and give up after 2
    consecutive failures rather than blocking the whole ten-specialist run.
    Production would use 30 years of ERA5.
    """
    import time
    t0 = time.monotonic()
    budget_sec = 22.0
    consecutive_failures = 0
    target = date.fromisoformat(target_date)
    # We'll fetch one query per year and average
    # (ERA5 archive doesn't support multi-year queries efficiently)
    all_sst: list[float] = []
    all_wave: list[float] = []
    for years_ago in range(1, window_years + 1):
        if time.monotonic() - t0 > budget_sec:
            print("[Anomaly] baseline time budget exhausted — using partial data", file=sys.stderr)
            break
        if consecutive_failures >= 2:
            print("[Anomaly] archive attempts failed in this run — stopping early", file=sys.stderr)
            break
        try:
            past = target.replace(year=target.year - years_ago)
        except ValueError:
            # Feb 29 on a non-leap year
            past = target.replace(year=target.year - years_ago, day=28)
        start_str = past.isoformat()
        end_str = (past + timedelta(days=2)).isoformat()
        params = {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "daily": "sea_surface_temperature_max,wave_height_max",
            "start_date": start_str,
            "end_date": end_str,
            "timezone": "auto",
        }
        url = f"{ARCHIVE_URL}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ORCA/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
            sst_arr = data.get("daily", {}).get("sea_surface_temperature_max", [])
            wave_arr = data.get("daily", {}).get("wave_height_max", [])
            sst_v = [v for v in sst_arr if v is not None]
            wave_v = [v for v in wave_arr if v is not None]
            if sst_v:
                all_sst.append(sum(sst_v) / len(sst_v))
            if wave_v:
                all_wave.append(sum(wave_v) / len(wave_v))
            consecutive_failures = 0
        except Exception as e:  # noqa: BLE001
            print(f"[Anomaly] {past.year} fetch failed: {type(e).__name__}", file=sys.stderr)
            consecutive_failures += 1
            continue

    if not all_sst:
        return {}
    return {
        "baseline_sst_mean": round(sum(all_sst) / len(all_sst), 2),
        "baseline_sst_n": len(all_sst),
        "baseline_wave_mean": round(sum(all_wave) / len(all_wave), 2) if all_wave else None,
    }


def baseline_cached(lat: float, lon: float, target_date: str) -> dict:
    """_fetch_baseline through the shared TTL cache — ONE ERA5 walk per
    0.01° cell per day, shared by analyze() AND the zone-snapshot's
    parallel warm-up job (same key), so the ten-specialist run never pays the
    3 archive calls serially after the gather. (Serial payment is what
    pushed a cold /reason past its 110 s deadline on the 2026-09-07
    night run — URLError×2 at the very end of the request.)

    A real baseline keeps for 6 h (climatology changes ~never within a
    day); a TOTAL failure (empty dict) only 10 min — a dead archive
    minute must not poison the cell for hours, and the give-up-early
    path makes an honest re-miss cheap.
    """
    from pipeline.ttlcache import cached
    return cached(
        f"anom:{lat:.2f},{lon:.2f}:{target_date}",
        21_600,  # 6 h
        lambda: _fetch_baseline(lat, lon, target_date, window_years=3),
        ttl_for=lambda b: 21_600.0 if (b and b.get("baseline_sst_mean") is not None) else 600.0,
    ) or {}


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    lat = snap.get("lat")
    lon = snap.get("lon")
    target_date = snap.get("date")

    if lat is None or lon is None or target_date is None:
        return {
            "agent": "anomaly",
            "findings": [{
                "type": "no_location",
                "severity": "info",
                "value": None,
                "msg": "No lat/lon/date — cannot compute anomaly.",
            }],
            "summary": "No location data.",
            "risk_level": "unknown",
        }

    current_sst = snap.get("sst_mean") or snap.get("sst_max")

    try:
        # Shared cached helper — when the zone snapshot already warmed
        # this key inside its parallel gather, this is an instant hit.
        baseline = baseline_cached(lat, lon, target_date)
        if baseline is None:
            baseline = {}
    except urllib.error.HTTPError as e:
        return {
            "agent": "anomaly",
            "findings": [{
                "type": "baseline_api_error",
                "severity": "info",
                "value": e.code,
                "msg": f"ERA5 archive returned HTTP {e.code}.",
            }],
            "summary": "Anomaly baseline unavailable.",
            "risk_level": "unknown",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "agent": "anomaly",
            "findings": [{
                "type": "baseline_unreachable",
                "severity": "info",
                "value": None,
                "msg": f"ERA5 archive unreachable: {type(e).__name__}.",
            }],
            "summary": "Anomaly baseline unavailable.",
            "risk_level": "unknown",
        }

    if not baseline:
        return {
            "agent": "anomaly",
            "findings": [{
                "type": "no_baseline",
                "severity": "info",
                "value": None,
                "msg": "Could not build historical baseline (all years failed).",
            }],
            "summary": "No baseline available.",
            "risk_level": "unknown",
        }

    findings.append({
        "type": "baseline_built",
        "severity": "info",
        "value": baseline,
        "source": SOURCE_LABEL,
        "observed_for": target_date,
        "retrieved_at": snap.get("fetched_at"),
        "msg": f"Comparison sample contains {baseline['baseline_sst_n']} prior-year value(s); it is not climatology.",
    })

    # SST anomaly
    if current_sst is not None and baseline.get("baseline_sst_mean") is not None:
        delta = current_sst - baseline["baseline_sst_mean"]
        if abs(delta) >= 3.0:
            sev = "high"
            label = "3°C internal deviation flag"
        elif abs(delta) >= 2.0:
            sev = "warn"
            label = "2°C internal deviation flag"
        elif abs(delta) >= 1.0:
            sev = "info"
            label = "1°C internal deviation flag"
        else:
            sev = "good"
            label = "below the 1°C internal display flag"
        direction = "warmer" if delta > 0 else "cooler"
        findings.append({
            "type": "sst_anomaly",
            "severity": sev,
            "value": round(delta, 2),
            "unit": "degC",
            "source": SOURCE_LABEL,
            "observed_for": target_date,
            "retrieved_at": snap.get("fetched_at"),
            "baseline_sample_size": baseline["baseline_sst_n"],
            "msg": (
                f"SST {current_sst:.1f}°C is {abs(delta):.1f}°C {direction} than "
                f"the {baseline['baseline_sst_n']}-prior-year sample mean "
                f"({baseline['baseline_sst_mean']:.1f}°C) — {label}; not a heatwave diagnosis."
            ),
        })

    # A snapshot's wave_max spans a different aggregation window from this
    # baseline sample, so comparing their ratio would be dimensionally
    # misleading. Wave anomalies are intentionally not emitted.

    # Risk
    severities = [f["severity"] for f in findings]
    if "high" in severities or "critical" in severities:
        risk = "high"
    elif "warn" in severities:
        risk = "moderate"
    elif "good" in severities:
        risk = "low"
    else:
        risk = "unknown"

    if risk == "high":
        summary = "🔍 SST crossed the 3°C internal deviation flag; this is not a heatwave diagnosis."
    elif risk == "moderate":
        summary = "🔍 SST crossed the 2°C internal deviation flag; scientific validation is pending."
    elif risk == "low":
        summary = "🔍 SST difference is below the 1°C internal display flag for this small sample."
    else:
        summary = "🔍 Anomaly detection unavailable."

    return {
        "agent": "anomaly",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
        "source": SOURCE_LABEL,
    }
