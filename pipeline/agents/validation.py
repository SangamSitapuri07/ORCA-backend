"""Agent 9: Data Validation ✅

Checks missing, inconsistent, or abnormal data.
Ensures data quality before analysis.

Inputs: ZoneSnapshot
Outputs: dict of findings (severity = warn/error for issues, info for notes)
"""
from __future__ import annotations

from typing import Any


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    # Coverage check
    n_used = len(snap.get("data_sources_used", []))
    n_failed = len(snap.get("data_sources_failed", []))
    n_total = n_used + n_failed

    if n_total == 0:
        findings.append({
            "type": "no_sources",
            "severity": "error",
            "value": 0,
            "msg": "No data sources attempted — pipeline broken.",
        })
    elif n_used == 0:
        findings.append({
            "type": "all_sources_failed",
            "severity": "error",
            "value": 0,
            "msg": f"All {n_total} data sources failed. Check network and credentials.",
        })
    elif n_used < n_total / 2:
        findings.append({
            "type": "low_source_coverage",
            "severity": "warn",
            "value": f"{n_used}/{n_total}",
            "msg": f"Only {n_used} of {n_total} sources succeeded — analysis is partial.",
        })

    # Range checks
    chl = snap.get("chlorophyll")
    if chl is not None:
        if chl < 0 or chl > 100:
            findings.append({
                "type": "chl_out_of_range",
                "severity": "error",
                "value": chl,
                "msg": f"Chlorophyll {chl:.2f} mg/m³ outside physical range (0-100).",
            })
        elif chl == 0:
            findings.append({
                "type": "chl_zero",
                "severity": "warn",
                "value": 0,
                "msg": "Chlorophyll is exactly 0 — may be fill value or zero-data cell.",
            })

    sst = snap.get("sst_mean") or snap.get("sst_max")
    if sst is not None:
        if sst < -2 or sst > 40:
            findings.append({
                "type": "sst_out_of_range",
                "severity": "error",
                "value": sst,
                "msg": f"SST {sst:.1f}°C outside physical ocean range (-2 to 40).",
            })

    wave = snap.get("wave_max")
    if wave is not None and wave > 15:
        findings.append({
            "type": "wave_extreme",
            "severity": "warn",
            "value": wave,
            "msg": f"Max wave {wave}m — extreme, possibly a tropical cyclone.",
        })

    # Staleness
    fetched_at = snap.get("fetched_at")
    target_date = snap.get("date")
    if target_date and fetched_at:
        try:
            from datetime import datetime
            fa = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            td = datetime.fromisoformat(target_date)
            age_days = (fa - td).days
            if age_days > 7:
                findings.append({
                    "type": "stale_data",
                    "severity": "warn",
                    "value": age_days,
                    "msg": f"Snapshot is {age_days} days old relative to target date.",
                })
        except Exception:
            pass

    # Risk
    severities = [f["severity"] for f in findings]
    if "error" in severities:
        risk = "high"
    elif "warn" in severities:
        risk = "moderate"
    else:
        risk = "low"

    n_err = sum(1 for f in findings if f["severity"] == "error")
    n_warn = sum(1 for f in findings if f["severity"] == "warn")
    if n_err:
        summary = f"Data quality: {n_err} errors detected — analysis may be unreliable."
    elif n_warn:
        summary = f"Data quality: {n_warn} warnings, {n_used}/{n_total} sources OK."
    else:
        summary = f"Data quality: OK — {n_used} sources, all within physical ranges."

    return {
        "agent": "validation",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
    }
