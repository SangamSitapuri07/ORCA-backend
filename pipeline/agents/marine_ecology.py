"""Conservative marine-ecology context synthesis.

The integrated feeds provide SST, chlorophyll-a and optional GFW apparent
fishing activity. These observations can identify co-occurrence and gradients,
but they cannot by themselves diagnose upwelling, harmful algal blooms,
ecosystem health, species habitat, or catch productivity. This agent therefore
emits explicitly provisional context and never turns it into a safety or
fishing recommendation.
"""
from __future__ import annotations

from typing import Any


def _common_metadata(snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "observed_for": snap.get("chlorophyll_date") or snap.get("date"),
        "retrieved_at": snap.get("fetched_at"),
        "sources": [
            snap.get("chlorophyll_source", "chlorophyll source unavailable"),
            "Open-Meteo Marine API via ORCA snapshot",
        ],
    }


def analyze(snap: dict[str, Any], agent_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    del agent_results  # retained in the public agent signature for orchestration compatibility
    findings: list[dict[str, Any]] = []

    chlorophyll = snap.get("chlorophyll")
    sst = snap.get("sst_mean")
    if sst is None:
        sst = snap.get("sst_max")
    fishing_hours = snap.get("fishing_hours")
    metadata = _common_metadata(snap)

    if sst is not None and chlorophyll is not None:
        findings.append({
            "type": "sst_chlorophyll_coobservation",
            "severity": "info",
            "value": {"sst_c": sst, "chlorophyll_mg_m3": chlorophyll},
            **metadata,
            "msg": (
                f"Co-observation: SST {sst:.1f}°C and chlorophyll {chlorophyll:.2f} mg/m³. "
                "This alone does not establish upwelling, a harmful bloom, species habitat, or catch potential."
            ),
        })

    cmin = snap.get("chlorophyll_box_min")
    cmax = snap.get("chlorophyll_box_max")
    if cmin is not None and cmax is not None:
        findings.append({
            "type": "chlorophyll_patch_range",
            "severity": "info",
            "value": {"box_min_mg_m3": cmin, "box_max_mg_m3": cmax},
            "observed_for": snap.get("chlorophyll_date") or snap.get("date"),
            "retrieved_at": snap.get("fetched_at"),
            "source": snap.get("chlorophyll_source", "chlorophyll source unavailable"),
            "msg": (
                f"Sampled chlorophyll patch range: {cmin:.2f}–{cmax:.2f} mg/m³. "
                "A range is not a validated biological front or fish aggregation."
            ),
        })

    if chlorophyll is not None and fishing_hours is not None:
        findings.append({
            "type": "chlorophyll_gfw_coobservation",
            "severity": "info",
            "value": {"chlorophyll_mg_m3": chlorophyll, "gfw_apparent_fishing_hours": fishing_hours},
            "observed_for": {
                "chlorophyll": snap.get("chlorophyll_date") or snap.get("date"),
                "gfw_start": snap.get("fishing_window_start"),
                "gfw_end": snap.get("fishing_window_end"),
            },
            "retrieved_at": snap.get("fetched_at"),
            "sources": [
                snap.get("chlorophyll_source", "chlorophyll source unavailable"),
                "Global Fishing Watch v3 apparent-fishing activity report",
            ],
            "msg": (
                "Chlorophyll and apparent-fishing activity are both present. "
                "Co-occurrence does not prove catch, productivity, legality, or causation."
            ),
        })

    if not findings:
        summary = "Ecological synthesis unavailable — no compatible observation pair."
        status = "unavailable"
    else:
        summary = f"Ecological context: {len(findings)} provisional co-observation(s); no ecological or catch verdict."
        status = "context_only"

    return {
        "agent": "marine_ecology",
        "findings": findings,
        "summary": summary,
        "risk_level": "unknown",
        "status": status,
    }
