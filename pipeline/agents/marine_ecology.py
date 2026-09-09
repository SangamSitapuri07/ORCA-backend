"""Agent 5: Marine Ecology 🐟

Combines ocean, satellite, and weather information to identify
potential ecosystem and productivity changes.

This is a "synthesis" agent — it reads the other agents' findings
and looks for cross-cutting patterns:
  - Bloom + warm SST = possible ecosystem shift
  - Upwelling (cold SST) + high chlorophyll = rich feeding zone
  - Fleet presence + chlorophyll = validated fishing ground

Inputs: ZoneSnapshot + other agent results
Outputs: dict of findings
"""
from __future__ import annotations

from typing import Any


def analyze(snap: dict[str, Any], agent_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    agent_results = agent_results or []

    chl = snap.get("chlorophyll")
    sst_mean = snap.get("sst_mean") or snap.get("sst_max")
    fishing_hours = snap.get("fishing_hours")

    # Pattern 1: Upwelling signature = cold SST + high chlorophyll
    if sst_mean is not None and chl is not None:
        if sst_mean < 26 and chl > 1.5:
            findings.append({
                "type": "upwelling_signature",
                "severity": "good",
                "value": {"sst": sst_mean, "chl": chl},
                "msg": f"Cold SST ({sst_mean:.1f}°C) + high chlorophyll ({chl:.2f} mg/m³) — classic upwelling signature, rich feeding zone.",
            })

    # Pattern 2: Bloom risk = very high chlorophyll + warm SST
    if sst_mean is not None and chl is not None:
        if sst_mean > 28 and chl > 5:
            findings.append({
                "type": "bloom_risk",
                "severity": "warn",
                "value": {"sst": sst_mean, "chl": chl},
                "msg": f"Warm SST ({sst_mean:.1f}°C) + very high chlorophyll ({chl:.2f} mg/m³) — possible harmful algal bloom.",
            })

    # Pattern 3: Validated fishing ground = chlorophyll + active fishing
    if chl is not None and 0.5 <= chl <= 5.0 and fishing_hours is not None and fishing_hours > 10:
        findings.append({
            "type": "validated_fishing_ground",
            "severity": "good",
            "value": {"chl": chl, "fishing_hours": fishing_hours},
            "msg": f"Productive chlorophyll ({chl:.2f} mg/m³) + active fishing ({fishing_hours:.1f} hrs) — proven fishing ground.",
        })

    # Pattern 4a: Ecosystem profile (always emitted when any data exists).
    # Standard oceanographic productivity classes (chl mg/m³) and pelagic
    # thermal-habitat bands (SST °C) — the same bands the satellite and
    # ocean agents use, summarized as one ecological statement so the
    # agent never goes silent when data is present.
    if chl is not None or sst_mean is not None:
        notes: list[str] = []
        if chl is not None:
            if chl < 0.1:
                notes.append(f"chlorophyll {chl:.2f} mg/m³ → oligotrophic (very low productivity)")
            elif chl < 0.5:
                notes.append(f"chlorophyll {chl:.2f} mg/m³ → low-to-moderate productivity")
            elif chl < 1.5:
                notes.append(f"chlorophyll {chl:.2f} mg/m³ → productive waters")
            elif chl < 5.0:
                notes.append(f"chlorophyll {chl:.2f} mg/m³ → highly productive waters")
            else:
                notes.append(f"chlorophyll {chl:.2f} mg/m³ → bloom-level productivity")
        if sst_mean is not None:
            if sst_mean < 22:
                notes.append(f"SST {sst_mean:.1f}°C → cold / upwelling thermal regime")
            elif sst_mean <= 29:
                notes.append(f"SST {sst_mean:.1f}°C → optimal pelagic thermal habitat")
            else:
                notes.append(f"SST {sst_mean:.1f}°C → very warm waters")
        findings.append({
            "type": "ecosystem_profile",
            "severity": "info",
            "value": {"chl": chl, "sst": sst_mean},
            "msg": "Ecosystem profile: " + "; ".join(notes) + ".",
        })

    # Pattern 4b: Chlorophyll spatial gradient (food-concentration front
    # proxy). zone_snapshot carries box_min/box_max of the chlorophyll
    # patch around the point; a strong local gradient concentrates food
    # and is where pelagic fish aggregate.
    cmin = snap.get("chlorophyll_box_min")
    cmax = snap.get("chlorophyll_box_max")
    if (cmin is not None and cmax is not None and cmin > 0
            and cmax > cmin * 2 and cmax > 0.5):
        findings.append({
            "type": "chl_spatial_gradient",
            "severity": "good",
            "value": {"box_min": cmin, "box_max": cmax},
            "msg": (
                f"Strong chlorophyll gradient nearby ({cmin:.2f}→{cmax:.2f} mg/m³) — "
                "front-like boundary concentrates food; pelagic fish often aggregate along it."
            ),
        })

    # Pattern 4: Cross-agent consensus on recommendations
    if agent_results:
        recs = [a.get("summary", "") for a in agent_results if "summary" in a]
        good_count = sum(1 for r in recs if "good" in r.lower() or "recommend" in r.lower() or "favorable" in r.lower())
        warn_count = sum(1 for r in recs if "warn" in r.lower() or "concern" in r.lower() or "caution" in r.lower())
        if good_count > 0 and warn_count == 0:
            findings.append({
                "type": "multi_agent_consensus_positive",
                "severity": "good",
                "value": good_count,
                "msg": f"{good_count} agents report positive conditions — strong consensus.",
            })
        elif warn_count > good_count:
            findings.append({
                "type": "multi_agent_consensus_negative",
                "severity": "warn",
                "value": warn_count,
                "msg": f"{warn_count} agents report concerns — proceed with caution.",
            })

    # Risk
    severities = [f["severity"] for f in findings]
    if "high" in severities or "critical" in severities:
        risk = "high"
    elif "warn" in severities:
        risk = "moderate"
    elif "good" in severities or "info" in severities:
        # Data present, nothing worrying detected → low ecological concern
        risk = "low"
    else:
        risk = "unknown"

    # Summary
    if not findings:
        summary = "No ecosystem patterns detected from current data."
    else:
        summary = f"Ecology: {len(findings)} pattern(s) detected — " + "; ".join(
            f["type"] for f in findings[:3]
        ) + "."

    return {
        "agent": "marine_ecology",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
    }
