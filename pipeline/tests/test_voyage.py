"""Voyage engine tests — pure scoring/reasons pin, no network."""
from pipeline.voyage import _score, _reasons, _point_state_stub, PFZ_BONUS, BLOOM_BONUS


def test_score_never_invents_safety():
    # danger can never outrank calm — even an official PFZ
    calm = _score("good", "hotspot", None, 20.0)
    danger = _score("danger", "pfz", 8.5, 20.0)
    assert danger < calm
    assert danger <= 100 + PFZ_BONUS + BLOOM_BONUS - 80


def test_score_terms_add_up():
    base = 100 + PFZ_BONUS + BLOOM_BONUS - int(10 * 0.15 + 0.5)  # good pfz bloom 10NM
    assert _score("good", "pfz", 8.5, 10.0) == base
    # distance always costs, never negative score
    assert _score("caution", "hotspot", None, 600.0) == 0


def test_reasons_are_auditable():
    row = {"state": "caution", "why": "waves up to 3.0 m", "wave_m": 2.6}
    rs = _reasons(row, "pfz", 8.5, 12.0,
                  {"advisory_date": "2026-09-09", "sector_name": "Maharashtra"})
    j = " | ".join(rs)
    assert "INCOIS PFZ" in j and "+20" in j
    assert "8.5" in j and "+10" in j
    assert "waves up to 3.0 m" in j and "−40" in j
    assert "12 NM" in j and "−2" in j


def test_reasons_unknown_weather_is_not_safe():
    row = _point_state_stub(None)  # fetch failed → unknown
    assert row["state"] == "unknown"
    rs = _reasons(row, "hotspot", None, 30.0, None)
    assert all("+20" not in r for r in rs)  # neutral, no pretending
    assert any("−" in r for r in rs)        # except honest distance cost
