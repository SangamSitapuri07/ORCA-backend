"""Agent 7: Marine Risk 🚨

Combines ocean and weather conditions to generate
marine risk levels: Low / Moderate / High / Critical.

This is a "vessel safety" agent — it asks: "should a fisherman
go out today in this zone?"

Inputs: ZoneSnapshot + other agent results
Outputs: dict of findings + overall risk level
"""
from __future__ import annotations

from typing import Any


# Risk weights — a finding's weight IS its safety meaning.
# wave_caution = 2 (not 1): 2.5 m+ waves are the IMD small-craft
# caution threshold, so the vessel-safety verdict must ESCALATE to
# "moderate" whenever the ocean agent itself says "moderate". With the
# old weight of 1 the agent quoted a rough-seas warning yet concluded
# "low" — found via screenshot review 2026-09-04 (Mumbai 2.5 m,
# Andaman 2.74 m — Marine Risk stayed low while quoting the warning).
WEIGHTS = {
    "wave_warning_high": 5,
    "wave_caution": 2,
    "gust_storm": 4,
    "gale_gusts": 2,
    "storm_warning": 4,
    "gale_warning": 2,
    # fresh_breeze = 2 (was 1): a WARN-tier wind finding from the weather
    # agent must escalate the boat-safety verdict exactly like a WARN-tier
    # wave finding does — otherwise the panel quotes "Fresh breeze,
    # exercise caution" right under a green LOW banner. (Screenshot
    # review 2026-09-04: Vizag 10.2 m/s case.)
    "fresh_breeze": 2,
    "heavy_rain": 2,
    "sst_extreme": 1,
    "stale_data": 1,
    "low_source_coverage": 1,
    "all_sources_failed": 5,
    "bloom_risk": 2,
}

RISK_THRESHOLDS = {
    0: "low",
    2: "moderate",
    4: "high",
    8: "critical",
}


def _score_to_risk(score: int) -> str:
    if score >= 8:
        return "critical"
    if score >= 4:
        return "high"
    if score >= 2:
        return "moderate"
    return "low"


def analyze(snap: dict[str, Any], agent_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    score = 0
    agent_results = agent_results or []

    # Aggregate wave risk from ocean agent
    ocean_result = next((a for a in agent_results if a.get("agent") == "ocean"), {})
    for f in ocean_result.get("findings", []):
        if f["type"] == "wave_warning_high":
            score += WEIGHTS["wave_warning_high"]
            findings.append(f)
        elif f["type"] == "wave_caution":
            score += WEIGHTS["wave_caution"]
            findings.append(f)

    # Aggregate wind hazards from weather agent — a boat capsizes from
    # WIND as easily as from waves; the safety agent must see both.
    wx_result = next((a for a in agent_results if a.get("agent") == "weather"), {})
    for f in wx_result.get("findings", []):
        w = WEIGHTS.get(f["type"]) if f["type"] in WEIGHTS else None
        if w is None:
            # Severity-based fallback: an unlisted WARN/HIGH weather
            # finding (e.g. a thunderstorm condition code) must never be
            # silently ignored by the safety verdict.
            w = {"warn": 2, "high": 4, "critical": 5}.get(f.get("severity"), 0)
        if w:
            score += w
            findings.append(f)

    # Aggregate validation warnings
    val_result = next((a for a in agent_results if a.get("agent") == "validation"), {})
    for f in val_result.get("findings", []):
        if f["severity"] == "error":
            score += 2
            findings.append({
                "type": f["type"],
                "severity": "high",
                "value": f.get("value"),
                "msg": "Data error: " + f["msg"],
            })
        elif f["type"] == "low_source_coverage":
            score += 1
            findings.append(f)

    # Aggregate ecology warnings
    eco_result = next((a for a in agent_results if a.get("agent") == "marine_ecology"), {})
    for f in eco_result.get("findings", []):
        if f["type"] == "bloom_risk":
            score += 2
            findings.append(f)

    risk = _score_to_risk(score)
    color = {
        "low": "🟢",
        "moderate": "🟡",
        "high": "🟠",
        "critical": "🔴",
    }[risk]

    if risk == "critical":
        summary = f"{color} CRITICAL risk — DO NOT venture out. Multiple severe warnings active."
    elif risk == "high":
        summary = f"{color} HIGH risk — only experienced crew with appropriate vessels should consider going out."
    elif risk == "moderate":
        summary = f"{color} MODERATE risk — proceed with caution, monitor conditions."
    elif risk == "low":
        summary = f"{color} LOW risk — conditions acceptable for normal operations."
    else:
        summary = "Risk level unknown — insufficient data."

    return {
        "agent": "marine_risk",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
        "risk_score": score,
    }
