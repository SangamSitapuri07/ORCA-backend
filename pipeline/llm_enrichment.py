"""Optional Ollama explanations over already-computed agent findings.

The deterministic agent output remains authoritative. LLM text is attached in
separate fields and can neither alter risk levels nor the final safety verdict.
RAG is deliberately reported as unavailable until its real team source is
provided; live observations are never presented as retrieved documents.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pipeline.ollama_client import ollama

_ANALYTICAL_IDS = {
    "ocean_analysis",
    "satellite_analysis",
    "weather_hazard",
    "marine_ecology",
    "fisheries_pfz",
}

_SYSTEM = (
    "You are an analytical component inside ORCA. Use only the supplied "
    "structured evidence. Do not invent measurements, sources, timestamps, "
    "confidence, forecasts, or retrieval results. Do not make or modify a "
    "safety verdict: ORCA's deterministic marine-risk engine is authoritative."
)


def _evidence_for(agent: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    for finding in agent.get("findings", []):
        if not isinstance(finding, dict):
            continue
        message = finding.get("msg")
        if message:
            evidence.append(str(message))
    return evidence[:12]


def _interpret(agent: dict[str, Any]) -> tuple[str | None, int]:
    started = time.monotonic()
    evidence = _evidence_for(agent)
    prompt = (
        f"Agent: {agent.get('agent_id') or agent.get('agent')}\n"
        f"Deterministic risk tag: {agent.get('risk_level', 'unknown')}\n"
        "Evidence:\n- " + ("\n- ".join(evidence) if evidence else "No usable evidence") + "\n"
        "Give at most two short fisherman-friendly sentences. If the evidence "
        "is insufficient, say that directly."
    )
    text = ollama.generate(prompt, system=_SYSTEM)
    return text, int((time.monotonic() - started) * 1000)


def enrich_agents(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach bounded LLM interpretations to eligible real agent results."""
    eligible = [a for a in agents if a.get("agent_id") in _ANALYTICAL_IDS]
    available = ollama.is_available()

    for agent in eligible:
        agent["llm_attempted"] = available
        agent["llm_invoked"] = False
        agent["llm_model"] = ollama.model
        agent["llm_interpretation"] = None
        agent["rag_invoked"] = False
        agent["context_source"] = "live structured observations only"
        if not available:
            agent["execution_class"] = "DETERMINISTIC FALLBACK"
            agent["status"] = "degraded"

    if not available or not eligible:
        return agents

    with ThreadPoolExecutor(max_workers=len(eligible)) as pool:
        futures = {pool.submit(_interpret, agent): agent for agent in eligible}
        for future in as_completed(futures):
            agent = futures[future]
            try:
                text, elapsed_ms = future.result()
            except Exception as exc:  # noqa: BLE001
                text, elapsed_ms = None, 0
                agent["llm_error"] = f"{type(exc).__name__}: {exc}"
            agent["duration_ms"] = int(agent.get("duration_ms", 0)) + elapsed_ms
            agent["llm_invoked"] = text is not None
            agent["llm_interpretation"] = text
            agent["execution_class"] = "LLM + DETERMINISTIC" if text else "DETERMINISTIC FALLBACK"
            agent["status"] = "completed" if text else "degraded"

    return agents


def orchestrator_trace(
    agents: list[dict[str, Any]],
    *,
    overall_risk: str,
    summary: str,
    recommendation: str,
    fetched_at: str | None,
) -> dict[str, Any]:
    """Build the eleventh trace stage; verdict and recommendation stay deterministic."""
    evidence = [
        {
            "agent": a.get("agent_id") or a.get("agent"),
            "risk": a.get("risk_level"),
            "summary": a.get("summary"),
        }
        for a in agents
    ]
    started = time.monotonic()
    explanation = None
    if ollama.is_available():
        explanation = ollama.generate(
            "Deterministic overall risk: " + overall_risk + "\n"
            "Deterministic recommendation: " + recommendation + "\n"
            "Agent board: " + json.dumps(evidence, ensure_ascii=False) + "\n"
            "Explain the agreement or disagreement in at most three short sentences. "
            "Do not change the risk or recommendation.",
            system=_SYSTEM,
            max_tokens=220,
        )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "agent": "orca_reasoning",
        "agent_id": "orchestrator",
        "findings": [{
            "type": "deterministic_synthesis",
            "severity": "info",
            "value": overall_risk,
            "msg": summary,
        }],
        "summary": summary,
        "recommendation": recommendation,
        "risk_level": overall_risk,
        "status": "completed" if explanation else "degraded",
        "duration_ms": elapsed_ms,
        "execution_class": "LLM + DETERMINISTIC" if explanation else "DETERMINISTIC FALLBACK",
        "llm_attempted": ollama.enabled,
        "llm_invoked": explanation is not None,
        "llm_model": ollama.model,
        "llm_interpretation": explanation,
        "rag_invoked": False,
        "context_source": "live agent findings only",
        "fetched_at": fetched_at,
    }
