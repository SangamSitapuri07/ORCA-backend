"""Voyage engine tests — pure experimental ranking/reasons, no network."""
from pipeline.voyage import _score, _reasons, _point_state_stub, UNKNOWN_WEATHER_PENALTY


def test_score_never_invents_safety():
    verified = _score("good", "pfz", None, 20.0)
    unknown = _score("unknown", "pfz", None, 20.0)
    danger = _score("danger", "pfz", None, 20.0)
    assert verified > unknown > danger


def test_score_terms_add_up_without_chlorophyll_or_pfz_bonus():
    distance_penalty = int(10 * 0.15 + 0.5)
    assert _score("good", "pfz", 8.5, 10.0) == 100 - distance_penalty
    assert _score("unknown", "pfz", None, 10.0) == 100 - UNKNOWN_WEATHER_PENALTY - distance_penalty
    assert _score("caution", "pfz", None, 600.0) == 0


def test_reasons_are_auditable_and_do_not_score_chlorophyll():
    row = {"state": "caution", "why": "waves up to 3.0 m", "wave_m": 2.6}
    reasons = _reasons(
        row, "pfz", 8.5, 12.0,
        {"advisory_date": "2026-09-09", "sector_name": "Maharashtra"},
    )
    joined = " | ".join(reasons)
    assert "INCOIS PFZ" in joined and "eligibility only, +0" in joined
    assert "chlorophyll" not in joined.lower()
    assert "waves up to 3.0 m" in joined and "−40" in joined
    assert "12 NM" in joined and "−2" in joined


def test_reasons_unknown_weather_is_penalized_not_safe():
    row = _point_state_stub(None)
    assert row["state"] == "unknown"
    reasons = _reasons(
        row, "pfz", None, 30.0,
        {"advisory_date": "2026-09-09", "sector_name": "audit"},
    )
    assert any(f"−{UNKNOWN_WEATHER_PENALTY}" in reason for reason in reasons)
    assert any("not scored safe" in reason for reason in reasons)
