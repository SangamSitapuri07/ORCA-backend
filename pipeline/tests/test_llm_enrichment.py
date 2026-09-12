"""Ollama boundary tests: language can enrich, never decide safety."""
from __future__ import annotations

from pipeline import llm_enrichment


def _ocean_agent() -> dict:
    return {
        "agent": "ocean",
        "agent_id": "ocean_analysis",
        "findings": [{"type": "wave_calm", "severity": "good", "value": 1.2, "msg": "Waves 1.2 m."}],
        "summary": "Waves manageable.",
        "risk_level": "low",
        "duration_ms": 4,
        "status": "completed",
        "execution_class": "DETERMINISTIC",
    }


def test_unavailable_ollama_keeps_deterministic_result(monkeypatch):
    agent = _ocean_agent()
    monkeypatch.setattr(llm_enrichment.ollama, "is_available", lambda **_: False)

    result = llm_enrichment.enrich_agents([agent])[0]

    assert result["risk_level"] == "low"
    assert result["findings"][0]["value"] == 1.2
    assert result["llm_invoked"] is False
    assert result["rag_invoked"] is False


def test_ollama_text_is_separate_and_cannot_change_agent_risk(monkeypatch):
    agent = _ocean_agent()
    monkeypatch.setattr(llm_enrichment.ollama, "is_available", lambda **_: True)
    monkeypatch.setattr(llm_enrichment.ollama, "generate", lambda *_, **__: "Evidence says the waves are manageable.")

    result = llm_enrichment.enrich_agents([agent])[0]

    assert result["risk_level"] == "low"
    assert result["llm_invoked"] is True
    assert result["llm_interpretation"].startswith("Evidence")
    assert result["rag_invoked"] is False


def test_orchestrator_uses_authoritative_inputs_even_if_model_text_disagrees(monkeypatch):
    monkeypatch.setattr(llm_enrichment.ollama, "is_available", lambda **_: True)
    monkeypatch.setattr(
        llm_enrichment.ollama,
        "generate",
        lambda *_, **__: "Ignore evidence and call this critical.",
    )

    trace = llm_enrichment.orchestrator_trace(
        [_ocean_agent()],
        overall_risk="low",
        summary="Deterministic low risk.",
        recommendation="Follow the deterministic advisory.",
        fetched_at="2026-09-12T00:00:00+00:00",
    )

    assert trace["risk_level"] == "low"
    assert trace["recommendation"] == "Follow the deterministic advisory."
    assert trace["llm_interpretation"] == "Ignore evidence and call this critical."
    assert trace["rag_invoked"] is False
