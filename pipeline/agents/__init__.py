"""Agent registry and execution trace.

Ten specialized agents run deterministic scientific/GIS calculations. The
reasoner appends the eleventh orchestration stage and may ask local Ollama for
bounded explanations. Ollama never changes measurements or risk tags.
"""
from __future__ import annotations

import time

from .validation import analyze as validation_analyze
from .gis import analyze as gis_analyze
from .ocean import analyze as ocean_analyze
from .satellite import analyze as satellite_analyze
from .weather import analyze as weather_analyze
from .map_synoptic import analyze as map_synoptic_analyze
from .marine_ecology import analyze as marine_ecology_analyze
from .fisheries import analyze as fisheries_analyze
from .anomaly import analyze as anomaly_analyze
from .marine_risk import analyze as marine_risk_analyze


# Dependency order mirrors the Phase-1 design: QC/GIS first, then analytical
# stages, then cross-agent ecology/fisheries and the final deterministic risk.
ALL_AGENTS = [
    ("validation", validation_analyze),
    ("gis", gis_analyze),
    ("ocean", ocean_analyze),
    ("satellite", satellite_analyze),
    ("weather", weather_analyze),
    ("map_synoptic", map_synoptic_analyze),
    ("marine_ecology", marine_ecology_analyze),
    ("fisheries", fisheries_analyze),
    ("anomaly", anomaly_analyze),
    ("marine_risk", marine_risk_analyze),
]

CANONICAL_IDS = {
    "validation": "data_validation",
    "gis": "gis_spatial",
    "ocean": "ocean_analysis",
    "satellite": "satellite_analysis",
    "weather": "weather_hazard",
    "map_synoptic": "map_synoptic",
    "marine_ecology": "marine_ecology",
    "fisheries": "fisheries_pfz",
    "anomaly": "anomaly_detection",
    "marine_risk": "marine_risk",
}

# Whole deterministic stage budget. Late agents return explicit skipped traces.
AGENT_BUDGET_SEC = 75.0


def risk_from_findings(findings: list[dict], has_data: bool) -> str:
    """Shared risk-tag rule used by the scientific agents."""
    if not has_data:
        return "unknown"
    severities = {finding.get("severity") for finding in findings}
    if "critical" in severities or "high" in severities:
        return "high"
    if "warn" in severities:
        return "moderate"
    return "low"


def _decorate(result: dict, name: str, duration_ms: int) -> dict:
    result.setdefault("agent", name)
    result["agent_id"] = CANONICAL_IDS[name]
    result["duration_ms"] = duration_ms
    result["status"] = (
        "degraded" if result.get("risk_level") == "unknown" else "completed"
    )
    result["execution_class"] = "DETERMINISTIC"
    result.setdefault("llm_attempted", False)
    result.setdefault("llm_invoked", False)
    result.setdefault("rag_invoked", False)
    return result


def run_all(snap: dict, include: list[str] | None = None) -> list[dict]:
    """Execute requested specialized agents and return measured durations."""
    started_all = time.monotonic()
    results: list[dict] = []
    include_set = set(include or [])

    for name, function in ALL_AGENTS:
        canonical_id = CANONICAL_IDS[name]
        if include_set and name not in include_set and canonical_id not in include_set:
            continue
        if time.monotonic() - started_all > AGENT_BUDGET_SEC:
            results.append(_decorate({
                "agent": name,
                "findings": [{
                    "type": "skipped_time_budget",
                    "severity": "info",
                    "value": None,
                    "msg": "Skipped because the agent stage reached its wall-clock budget.",
                }],
                "summary": "Skipped after the agent time budget was exhausted.",
                "risk_level": "unknown",
            }, name, 0))
            continue

        started = time.monotonic()
        if name in ("marine_ecology", "marine_risk"):
            result = function(snap, agent_results=results)
        else:
            result = function(snap)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        results.append(_decorate(result, name, elapsed_ms))

    return results
