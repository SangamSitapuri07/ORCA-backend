"""Agent registry — maps agent name to its analyze() function.

All 9 functional agents (Ocean, Satellite, Weather, GIS, Fisheries,
Marine Ecology, Marine Risk, Anomaly, Data Validation) are in this
package. Agent 10 (ORCA Reasoning) is in pipeline/reasoner.py.

To add a new agent:
  1. Drop a file in this directory with a top-level `analyze(snap, ...)` function
  2. Register it in ALL_AGENTS below
"""
from .ocean import analyze as ocean_analyze
from .satellite import analyze as satellite_analyze
from .weather import analyze as weather_analyze
from .gis import analyze as gis_analyze
from .fisheries import analyze as fisheries_analyze
from .marine_ecology import analyze as marine_ecology_analyze
from .marine_risk import analyze as marine_risk_analyze
from .anomaly import analyze as anomaly_analyze
from .validation import analyze as validation_analyze


ALL_AGENTS = [
    ("ocean", ocean_analyze),
    ("satellite", satellite_analyze),
    ("weather", weather_analyze),
    ("gis", gis_analyze),
    ("fisheries", fisheries_analyze),
    ("marine_ecology", marine_ecology_analyze),
    ("marine_risk", marine_risk_analyze),
    ("anomaly", anomaly_analyze),
    ("validation", validation_analyze),
]


# Hard wall-clock budget for the whole agent stage. On slow networks a
# chain of 9 agents with network calls can otherwise run for minutes and
# the UI times out waiting (seen on the laptop: /reason > 220 s). Rather
# skip late agents honestly than answer late.
AGENT_BUDGET_SEC = 75.0


def risk_from_findings(findings: list[dict], has_data: bool) -> str:
    """ONE shared rule for every agent's tag (centralized 2026-09-05).

    Reason this exists: the same "no data" mislabel kept re-appearing
    agent-by-agent — first Satellite (bug #3), then Weather — because
    each agent derived its tag with its own ad-hoc severity counting,
    and a day whose readings were all informational fell through to
    "unknown" even though real live values were displayed below.

    The single rule:
      - has_data=False          -> "unknown"   (truly nothing measured)
      - any severity high/crit  -> "high"
      - any severity warn       -> "moderate"
      - otherwise (data exists) -> "low"       (real readings, no hazard)
    "info" findings with has_data=True mean we measured safe conditions;
    that is a *good* answer, never "no data".
    """
    if not has_data:
        return "unknown"
    sevs = {f.get("severity") for f in findings}
    if "critical" in sevs or "high" in sevs:
        return "high"
    if "warn" in sevs:
        return "moderate"
    return "low"


def run_all(snap: dict, include: list[str] | None = None) -> list[dict]:
    """Run the requested agents (or all by default) and return their results.

    Each agent gets the snapshot and (optionally) a list of previously-run
    agent results for cross-agent synthesis (ecology, risk). Agents past
    the shared time budget are skipped with an honest placeholder instead
    of making the whole insight late.
    """
    import time
    t0 = time.monotonic()
    results: list[dict] = []
    for name, fn in ALL_AGENTS:
        if include and name not in include:
            continue
        if time.monotonic() - t0 > AGENT_BUDGET_SEC:
            results.append({
                "agent": name,
                "findings": [{
                    "type": "skipped_time_budget",
                    "severity": "info",
                    "value": None,
                    "msg": "Skipped — slow network: the 10-agent run hit its time budget. "
                           "Try again; cached sources make the second run faster.",
                }],
                "summary": "Skipped (slow network).",
                "risk_level": "unknown",
            })
            continue
        # Ecology and Risk want to see other agents' results
        if name in ("marine_ecology", "marine_risk"):
            res = fn(snap, agent_results=results)
        else:
            res = fn(snap)
        results.append(res)
    return results
