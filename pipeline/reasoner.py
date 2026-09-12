"""ORCA Reasoning & Orchestration Agent 🧠

Coordinates all agents. Combines their findings and resolves conflicts.
Generates the final explainable marine ecosystem insight.

This is the "brain" of ORCA. It:
  1. Receives a ZoneSnapshot
  2. Runs ten specialized agents in dependency order
  3. Aggregates risks (max of all agent risks)
  4. Synthesizes a final answer with source attribution
  5. Returns explainable text + structured findings

Usage:
    from pipeline.orca_data import zone_snapshot
    from pipeline.reasoner import reason

    snap = zone_snapshot(19.0, 72.8, "2026-08-15")
    insight = reason(snap)
    # Returns: {
    #   "zone": {...snapshot...},
    #   "agents": [<ten specialist results + orchestrator>],
    #   "overall_risk": "low" | "moderate" | "high" | "critical",
    #   "summary": "Human-readable explanation",
    #   "recommendation": "Should a fisherman go out today?",
    # }
"""
from __future__ import annotations

from typing import Any

from pipeline.agents import run_all
from pipeline.llm_enrichment import enrich_agents, orchestrator_trace


RISK_ORDER = {"low": 0, "unknown": 1, "moderate": 2, "high": 3, "critical": 4}

# The validation agent is META: it rates how much DATA we have, not how
# dangerous the sea is. Mixing its "moderate" (some sources failed) into
# the environmental risk made the UI scream MODERATE on a calm sea
# whenever a remote source timed out — wrong message to a fisherman.
META_AGENTS = {"validation", "gis", "map_synoptic"}


def _max_risk(risks: list[str]) -> str:
    if not risks:
        return "unknown"
    return max(risks, key=lambda r: RISK_ORDER.get(r, 0))


def reason(
    snap: dict[str, Any],
    include_agents: list[str] | None = None,
) -> dict[str, Any]:
    """Run the full multi-agent reasoning on a ZoneSnapshot.

    Returns a dict with all agent results, an aggregated risk level,
    a human-readable summary, and an actionable recommendation.
    """
    agents = enrich_agents(run_all(snap, include=include_agents))

    # Aggregate risks — from agents that actually measured the sea.
    # "unknown" (input data missing) is NOT a risk level: a calm sea with
    # a dead satellite feed is still a calm sea. We track data coverage
    # separately so the UI can be honest about confidence.
    env_agents = [a for a in agents if a.get("agent") not in META_AGENTS]
    known_risks = [
        a.get("risk_level", "unknown") for a in env_agents
        if a.get("risk_level", "unknown") != "unknown"
    ]
    overall = _max_risk(known_risks) if known_risks else "unknown"

    data_coverage = {
        "known": len(known_risks),
        "total": len(env_agents),
        "sources_failed": len(snap.get("data_sources_failed", [])),
    }
    limited = data_coverage["known"] < data_coverage["total"]

    # Get key agent signals
    sat = next((a for a in agents if a["agent"] == "satellite"), {})
    ocean = next((a for a in agents if a["agent"] == "ocean"), {})
    eco = next((a for a in agents if a["agent"] == "marine_ecology"), {})
    risk_agent = next((a for a in agents if a["agent"] == "marine_risk"), {})

    # Build summary
    parts = []
    # PFZ/catch suitability is intentionally absent: this analytical snapshot
    # does not include an official INCOIS PFZ advisory, and ORCA no longer
    # manufactures a score from generic SST/chlorophyll/AIS observations.
    if risk_agent.get("summary"):
        # Label it: this is the vessel-safety AGENT's verdict. The big
        # banner above is the OVERALL (max across all agents). Unlabeled,
        # the two read as contradictions when they diverge.
        parts.append(f"Vessel-safety: {risk_agent['summary']}")

    if ocean.get("summary") and ocean["summary"] != "No ocean data available for this zone.":
        parts.append(f"Ocean: {ocean['summary']}")

    if sat.get("summary") and "unavailable" not in sat["summary"]:
        parts.append(f"Satellite: {sat['summary']}")

    summary = " | ".join(parts) if parts else "Insufficient data for recommendation."

    # This endpoint is an analytical trace, not the skipper-verdict endpoint.
    # Known wave/weather hazards may be surfaced, but LOW is never converted to
    # GO here because cyclone completeness and the full advisory evidence gate
    # belong to /api/v1/advisory.
    safety_risk = risk_agent.get("risk_level", "unknown")
    if safety_risk in ("critical", "high"):
        rec = "🛑 A wave/weather hazard crossed an ORCA threshold. Use the skipper advisory and official IMD/INCOIS bulletins before departure."
    elif safety_risk == "moderate":
        rec = "🟡 A wave/weather caution threshold was crossed. Use /api/v1/advisory for the complete skipper verdict."
    else:
        rec = "❓ This analytical trace does not issue GO. Use /api/v1/advisory, which requires complete wave, wind, gust, weather, and cyclone evidence."

    # Honest confidence note: risk came only from agents with real inputs.
    if limited and overall != "unknown":
        rec += (
            f" (Coverage: {data_coverage['known']}/{data_coverage['total']} "
            f"analytical agents had a known status; {data_coverage['sources_failed']} source failure(s).)"
        )

    # Backend-owned precaution signal. This endpoint never emits GO; only the
    # deterministic advisory endpoint has the complete evidence/cyclone gate.
    verdict = {
        "moderate": "caution",
        "high": "no_go",
        "critical": "no_go",
    }.get(safety_risk, "unknown")

    trace = None
    requested = set(include_agents or [])
    if include_agents is None or requested.intersection({"orchestrator", "orca_reasoning"}):
        trace = orchestrator_trace(
            agents,
            overall_risk=overall,
            summary=summary,
            recommendation=rec,
            fetched_at=snap.get("fetched_at"),
        )
        agents.append(trace)

    llm_used = bool(trace and trace.get("llm_invoked"))
    return {
        "zone": {
            "lat": snap.get("lat"),
            "lon": snap.get("lon"),
            "date": snap.get("date"),
        },
        "agents": agents,
        "overall_risk": overall,
        "overall_risk_scope": "cross-agent analytical context; not the skipper safety verdict",
        "safety_signal": safety_risk,
        "verdict": verdict,
        "verdict_authority": "/api/v1/advisory",
        "summary": summary,
        "recommendation": rec,
        "orchestrator_synthesis": {
            "headline": summary,
            "recommendation": rec,
            "trace_owner": (
                f"Ollama {trace.get('llm_model')} + deterministic reasoner"
                if llm_used else "Deterministic reasoner (Ollama unavailable or disabled)"
            ),
            "timestamp": snap.get("fetched_at"),
            "llm_interpretation": trace.get("llm_interpretation") if trace else None,
            "rag_invoked": False,
            "context_source": "live agent findings only",
        },
        "data_coverage": {
            **data_coverage,
            "failed_sources": snap.get("data_sources_failed", []),
        },
        "data_sources_used": snap.get("data_sources_used", []),
        "data_sources_failed": snap.get("data_sources_failed", []),
        "fetched_at": snap.get("fetched_at"),
    }
