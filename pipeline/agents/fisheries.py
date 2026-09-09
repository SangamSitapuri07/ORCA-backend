"""Agent 6: Fisheries / PFZ 🎣

Analyzes SST, chlorophyll, currents, and PFZ data to identify
potentially suitable fishing zones.

Combines the satellite + ocean signals with the GFW fishing-effort
ground truth to give a per-zone PFZ verdict:
  - "highly_recommended"
  - "recommended"
  - "neutral"
  - "not_recommended"
  - "unknown"

Inputs: ZoneSnapshot
Outputs: dict of findings
"""
from __future__ import annotations

from typing import Any
import math


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    verdict = "unknown"  # default if no signals at all

    chl = snap.get("chlorophyll")
    sst = snap.get("sst_mean") or snap.get("sst_max")
    fishing_hours = snap.get("fishing_hours")
    pfz_score = snap.get("pfz_score")
    fleet_by_flag = snap.get("fleet_by_flag") or {}
    by_gear = snap.get("fleet_by_gear") or {}

    # 1) PFZ score (from orca_data, already 0-1)
    if pfz_score is not None:
        if pfz_score >= 0.7:
            verdict = "highly_recommended"
            sev = "good"
            msg = f"PFZ composite score {pfz_score:.2f} — highly recommended fishing zone."
        elif pfz_score >= 0.5:
            verdict = "recommended"
            sev = "good"
            msg = f"PFZ composite score {pfz_score:.2f} — recommended fishing zone."
        elif pfz_score >= 0.3:
            verdict = "neutral"
            sev = "info"
            msg = f"PFZ composite score {pfz_score:.2f} — neutral, no strong signal."
        else:
            verdict = "not_recommended"
            sev = "warn"
            msg = f"PFZ composite score {pfz_score:.2f} — conditions not favorable."
        findings.append({
            "type": "pfz_verdict",
            "severity": sev,
            "value": pfz_score,
            "msg": msg,
        })

    # 2) Chlorophyll productive band (0.5-1.5 = best for pelagics)
    if chl is not None and chl > 0:
        if 0.5 <= chl <= 1.5:
            findings.append({
                "type": "chl_pfz_sweet_spot",
                "severity": "good",
                "value": chl,
                "msg": f"Chlorophyll {chl:.2f} mg/m³ in the productive band favored by INCOIS PFZ algorithm.",
            })
        elif 1.5 < chl <= 5.0:
            findings.append({
                "type": "chl_high_bloom",
                "severity": "good",
                "value": chl,
                "msg": f"Chlorophyll {chl:.2f} mg/m³ — high bloom zone, may attract baitfish.",
            })

    # 3) SST for pelagics (24-29°C)
    if sst is not None and 24 <= sst <= 29:
        findings.append({
            "type": "sst_pelagic_optimal",
            "severity": "good",
            "value": sst,
            "msg": f"SST {sst:.1f}°C in the pelagic-fish sweet spot (24-29°C).",
        })

    # 4) Fishing-effort ground truth
    if fishing_hours is not None and fishing_hours > 0:
        if fishing_hours >= 50:
            findings.append({
                "type": "high_fishing_activity",
                "severity": "info",
                "value": fishing_hours,
                "msg": f"Active fishing: {fishing_hours:.1f} hours in 30 days — proven productive zone.",
            })
        elif fishing_hours >= 5:
            findings.append({
                "type": "moderate_fishing_activity",
                "severity": "info",
                "value": fishing_hours,
                "msg": f"Some fishing: {fishing_hours:.1f} hours in 30 days.",
            })
        else:
            findings.append({
                "type": "low_fishing_activity",
                "severity": "info",
                "value": fishing_hours,
                "msg": f"Light fishing: {fishing_hours:.1f} hours in 30 days (unexplored or low-density).",
            })

    # 5) Fleet composition (country + gear) — useful for what to expect
    if fleet_by_flag:
        countries = ", ".join(f"{k}({v})" for k, v in
                              sorted(fleet_by_flag.items(), key=lambda x: -x[1])[:3])
        findings.append({
            "type": "fleet_countries",
            "severity": "info",
            "value": fleet_by_flag,
            "msg": f"Fleet by country: {countries}.",
        })
    if by_gear:
        gears = ", ".join(f"{k}({v})" for k, v in
                          sorted(by_gear.items(), key=lambda x: -x[1])[:3])
        findings.append({
            "type": "fleet_gear",
            "severity": "info",
            "value": by_gear,
            "msg": f"Fleet by gear: {gears}.",
        })

    # Risk for fisheries = low if recommended, moderate if neutral, high if not
    if verdict == "highly_recommended" or verdict == "recommended":
        risk = "low"
    elif verdict == "neutral":
        risk = "moderate"
    elif verdict == "not_recommended":
        risk = "high"
    else:
        risk = "unknown"

    # Summary
    if verdict in ("highly_recommended", "recommended"):
        summary = f"Fishing verdict: {verdict.replace('_', ' ').title()}."
    elif verdict == "neutral":
        summary = "Fishing verdict: Neutral — neither good nor bad signals."
    elif verdict == "not_recommended":
        summary = "Fishing verdict: Not recommended — conditions unfavorable."
    else:
        summary = "Fishing verdict: Insufficient data."

    return {
        "agent": "fisheries",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
        "verdict": verdict,
    }
