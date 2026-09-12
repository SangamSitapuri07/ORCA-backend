"""Conservative satellite-observation agent.

Reports chlorophyll-a values and cross-source differences with provenance. A
chlorophyll concentration alone does not diagnose a harmful algal bloom,
upwelling, ecosystem health, fish presence, or catch suitability, so this agent
never converts it into a safety/fishing risk or recommendation.
"""
from __future__ import annotations

from typing import Any


def _ratio(a: float, b: float) -> float | None:
    if a <= 0 or b <= 0:
        return None
    return max(a, b) / min(a, b)


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    chlorophyll = snap.get("chlorophyll")
    source = snap.get("chlorophyll_source")
    unit = snap.get("chlorophyll_unit", "mg/m^3")
    observed_for = snap.get("chlorophyll_date") or snap.get("date")
    retrieved_at = snap.get("fetched_at")

    if chlorophyll is None:
        return {
            "agent": "satellite",
            "findings": [{
                "type": "no_chlorophyll_data",
                "severity": "info",
                "value": None,
                "source": source,
                "observed_for": observed_for,
                "retrieved_at": retrieved_at,
                "msg": f"No chlorophyll value is available from {source or 'the configured sources'}.",
            }],
            "summary": "Satellite chlorophyll unavailable.",
            "risk_level": "unknown",
            "status": "unavailable",
        }

    findings: list[dict[str, Any]] = [{
        "type": "chlorophyll_observation",
        "severity": "info",
        "value": chlorophyll,
        "unit": unit,
        "source": source,
        "observed_for": observed_for,
        "retrieved_at": retrieved_at,
        "msg": (
            f"Chlorophyll observation {chlorophyll:.2f} {unit}. This value alone "
            "does not identify HABs, fish, catch potential, or safety."
        ),
    }]

    occci = snap.get("chlorophyll_occci")
    if occci is not None:
        ratio = _ratio(float(chlorophyll), float(occci))
        findings.append({
            "type": "chlorophyll_occci_comparison",
            "severity": "info",
            "value": {"primary": chlorophyll, "occci": occci, "ratio": round(ratio, 2) if ratio else None},
            "unit": unit,
            "sources": [source, snap.get("chlorophyll_occci_source", "ESA OC-CCI")],
            "observed_for": observed_for,
            "retrieved_at": retrieved_at,
            "comparison_status": "large_difference" if ratio and ratio > 3 else "within_internal_display_band",
            "msg": (
                f"Primary and OC-CCI values differ by {ratio:.1f}×. "
                if ratio else "Primary and OC-CCI values cannot form a positive-value ratio. "
            ) + "The 3× band is an ORCA display flag, not scientific validation or confirmation.",
        })
    else:
        findings.append({
            "type": "chlorophyll_occci_unavailable",
            "severity": "info",
            "value": None,
            "source": "ESA OC-CCI",
            "observed_for": observed_for,
            "retrieved_at": retrieved_at,
            "msg": "Independent OC-CCI comparison is unavailable; no cause (such as cloud) is assumed without provider evidence.",
        })

    mosdac = snap.get("chlorophyll_mosdac")
    if mosdac is not None:
        ratio = _ratio(float(chlorophyll), float(mosdac))
        findings.append({
            "type": "chlorophyll_mosdac_comparison",
            "severity": "info",
            "value": {
                "primary": chlorophyll,
                "mosdac": mosdac,
                "ratio": round(ratio, 2) if ratio else None,
                "mosdac_pixel_km": snap.get("chlorophyll_mosdac_pixel_km"),
                "mosdac_ring_median": snap.get("chlorophyll_mosdac_ring_median"),
                "mosdac_ring_valid": snap.get("chlorophyll_mosdac_ring_valid"),
                "mosdac_area_median": snap.get("chlorophyll_mosdac_area_median"),
            },
            "unit": unit,
            "sources": [source, snap.get("chlorophyll_mosdac_source", "ISRO MOSDAC OCM-3")],
            "observed_for": {
                "primary": observed_for,
                "mosdac": snap.get("chlorophyll_mosdac_date"),
            },
            "retrieved_at": retrieved_at,
            "comparison_status": "large_difference" if ratio and ratio > 3 else "within_internal_display_band",
            "msg": (
                f"Primary and MOSDAC values differ by {ratio:.1f}×. "
                if ratio else "Primary and MOSDAC values cannot form a positive-value ratio. "
            ) + "No bloom, bias, cloud, or confirmation cause is inferred automatically.",
        })

    return {
        "agent": "satellite",
        "findings": findings,
        "summary": f"Satellite context: chlorophyll {chlorophyll:.2f} {unit}; no ecological, catch, or safety verdict.",
        "risk_level": "unknown",
        "status": "context_only",
    }
