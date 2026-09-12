"""Deterministic fisheries-context agent.

This agent reports measured chlorophyll, SST and Global Fishing Watch activity
with their available provenance. It deliberately does not convert those inputs
into a Potential Fishing Zone (PFZ) score or catch recommendation. ORCA has no
validated species/season model, and observed AIS activity is not proof of catch
or productivity. Official INCOIS PFZ advisories are handled by the separate
``/api/v1/voyage`` provider boundary.
"""
from __future__ import annotations

from typing import Any


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    fetched_at = snap.get("fetched_at")

    chlorophyll = snap.get("chlorophyll")
    if chlorophyll is not None:
        findings.append({
            "type": "chlorophyll_observation",
            "severity": "info",
            "value": chlorophyll,
            "unit": snap.get("chlorophyll_unit", "mg/m^3"),
            "observed_for": snap.get("chlorophyll_date") or snap.get("date"),
            "retrieved_at": fetched_at,
            "source": snap.get("chlorophyll_source", "snapshot source unavailable"),
            "msg": (
                f"Chlorophyll observation: {chlorophyll:.2f} "
                f"{snap.get('chlorophyll_unit', 'mg/m^3')}. No catch inference was made."
            ),
        })

    sst = snap.get("sst_mean")
    if sst is None:
        sst = snap.get("sst_max")
    if sst is not None:
        findings.append({
            "type": "sst_observation",
            "severity": "info",
            "value": sst,
            "unit": "degC",
            "observed_for": snap.get("date"),
            "retrieved_at": fetched_at,
            "source": "Open-Meteo Marine API via ORCA snapshot",
            "msg": f"Sea-surface-temperature observation: {sst:.1f}°C. No species suitability inference was made.",
        })

    fishing_hours = snap.get("fishing_hours")
    if fishing_hours is not None:
        start = snap.get("fishing_window_start")
        end = snap.get("fishing_window_end")
        radius = snap.get("fishing_bbox_radius_deg")
        findings.append({
            "type": "gfw_fishing_activity",
            "severity": "info",
            "value": fishing_hours,
            "unit": "reported hours",
            "window_start": start,
            "window_end": end,
            "bbox_half_width_deg": radius,
            "retrieved_at": fetched_at,
            "source": "Global Fishing Watch v3 apparent-fishing activity report",
            "msg": (
                f"GFW reported {fishing_hours:.1f} apparent-fishing hours"
                + (f" from {start} to {end}" if start and end else "")
                + ". Activity does not establish catch or productivity."
            ),
        })

    fleet_by_flag = snap.get("fleet_by_flag") or {}
    fleet_by_gear = snap.get("fleet_by_gear") or {}
    if fleet_by_flag:
        findings.append({
            "type": "gfw_fleet_flags",
            "severity": "info",
            "value": fleet_by_flag,
            "window_start": snap.get("fishing_window_start"),
            "window_end": snap.get("fishing_window_end"),
            "retrieved_at": fetched_at,
            "source": "Global Fishing Watch v3 vessel search/report",
            "msg": "GFW vessel flag categories are context only; they do not establish identity, legality, or catch.",
        })
    if fleet_by_gear:
        findings.append({
            "type": "gfw_fleet_gear",
            "severity": "info",
            "value": fleet_by_gear,
            "window_start": snap.get("fishing_window_start"),
            "window_end": snap.get("fishing_window_end"),
            "retrieved_at": fetched_at,
            "source": "Global Fishing Watch v3 vessel search/report",
            "msg": "GFW gear categories are provider classifications and are not a fishing recommendation.",
        })

    findings.append({
        "type": "official_pfz_not_evaluated",
        "severity": "info",
        "value": None,
        "source": "INCOIS PFZ adapter is available through /api/v1/voyage",
        "msg": "No official INCOIS PFZ advisory was attached to this snapshot; no PFZ verdict was generated.",
    })

    return {
        "agent": "fisheries",
        "findings": findings,
        "summary": "Fisheries observations are context only; official PFZ status was not evaluated here.",
        "risk_level": "unknown",
        "verdict": "unavailable",
        "status": "degraded",
    }
