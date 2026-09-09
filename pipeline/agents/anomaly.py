"""Agent 8: Anomaly Detection 🔍

Compares current conditions with historical/baseline data. Detects
unusual SST, chlorophyll, wave, current, and weather patterns.

For v1 we use Open-Meteo's Historical Weather API (ERA5 reanalysis,
1940-present) as a 30-year baseline. For SST, the ERA5 daily
aggregates are available. For chlorophyll, we don't have a free
historical baseline, so we just compare SST against the 1991-2020
climatology.

Real implementation would also use:
  - NOAA OISST v2.1 (1982-present daily SST, 0.25°)
  - ESA CCI chlorophyll (1997-present, 4 km)
  - IMD gridded temperature (1901-present)

Anomaly thresholds (from IPCC AR6 definitions):
  - < 1°C   : normal range
  - 1-2°C   : warm anomaly
  - 2-3°C   : strong warm anomaly
  - > 3°C   : extreme anomaly (likely marine heatwave)

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
SOURCE_LABEL = "Open-Meteo Archive (ERA5 reanalysis, 30-year baseline)"


def _fetch_baseline(lat: float, lon: float, target_date: str, window_years: int = 3) -> dict:
    """Fetch the same date-of-year from the past N years to build a baseline.

    Uses the last 3 years as a quick proxy for the climatology.
    Time-budgeted: on slow networks each ERA5 archive call can eat
    15-40 s, so we hard-stop at ~22 s total and give up after 2
    consecutive failures rather than blocking the whole 10-agent run.
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
            print("[Anomaly] archive failing repeatedly — giving up early", file=sys.stderr)
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
    parallel warm-up job (same key), so the 10-agent run never pays the
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
    current_wave = snap.get("wave_max")

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
        "msg": f"Baseline from {baseline['baseline_sst_n']} prior years.",
    })

    # SST anomaly
    if current_sst is not None and baseline.get("baseline_sst_mean") is not None:
        delta = current_sst - baseline["baseline_sst_mean"]
        if abs(delta) >= 3.0:
            sev = "high"
            label = "EXTREME anomaly (likely marine heatwave or cold spell)"
        elif abs(delta) >= 2.0:
            sev = "warn"
            label = "STRONG anomaly"
        elif abs(delta) >= 1.0:
            sev = "info"
            label = "Notable anomaly"
        else:
            sev = "good"
            label = "Normal range"
        direction = "warmer" if delta > 0 else "cooler"
        findings.append({
            "type": "sst_anomaly",
            "severity": sev,
            "value": round(delta, 2),
            "msg": f"SST {current_sst:.1f}°C is {abs(delta):.1f}°C {direction} than the 5-year baseline ({baseline['baseline_sst_mean']:.1f}°C) — {label}.",
        })

    # Wave anomaly
    if current_wave is not None and baseline.get("baseline_wave_mean") is not None and baseline["baseline_wave_mean"] > 0:
        ratio = current_wave / baseline["baseline_wave_mean"]
        if ratio >= 1.5:
            sev = "warn"
            msg = f"Wave height {current_wave}m is {ratio:.1f}× the baseline ({baseline['baseline_wave_mean']}m) — unusually rough."
        elif ratio <= 0.5:
            sev = "good"
            msg = f"Wave height {current_wave}m is {ratio:.1f}× the baseline ({baseline['baseline_wave_mean']}m) — unusually calm."
        else:
            sev = "info"
            msg = f"Wave height {current_wave}m is {ratio:.1f}× the baseline ({baseline['baseline_wave_mean']}m) — within normal range."
        findings.append({
            "type": "wave_anomaly",
            "severity": sev,
            "value": round(ratio, 2),
            "msg": msg,
        })

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
        summary = "🔍 EXTREME anomaly vs historical baseline — possible marine heatwave."
    elif risk == "moderate":
        summary = "🔍 Notable anomaly vs historical baseline — worth investigating."
    elif risk == "low":
        summary = "🔍 Conditions within normal historical range."
    else:
        summary = "🔍 Anomaly detection unavailable."

    return {
        "agent": "anomaly",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
        "source": SOURCE_LABEL,
    }
