"""B14 crowd-spread tests — pure/offline (store redirected to tmp)."""
from __future__ import annotations

import json

import pytest

from pipeline import crowd
from pipeline import voyage


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCA_CROWD_STORE", str(tmp_path / "crowd.json"))
    crowd.reset()
    from pipeline import ttlcache
    ttlcache.clear()
    yield
    crowd.reset()
    ttlcache.clear()


NOW = 1_800_000_000.0


def test_record_and_load_cells():
    crowd.record(15.11, 83.11, "pfz", ts=NOW)
    same = crowd.load(15.12, 83.12, ts=NOW)      # same 0.25° cell
    assert same["same_cell"] == 1 and same["effective"] == 1.0
    near = crowd.load(15.11, 83.41, ts=NOW)      # adjacent cell only
    assert near["same_cell"] == 0 and near["effective"] == 0.5
    far = crowd.load(18.00, 79.00, ts=NOW)       # far away
    assert far["effective"] == 0.0


def test_window_expiry():
    crowd.record(15.11, 83.11, "pfz", ts=NOW)    # 25 h old sighting
    assert crowd.load(15.11, 83.11, ts=NOW + 25 * 3600)["effective"] == 0.0
    assert crowd.load(15.11, 83.11, ts=NOW + 3600)["effective"] == 1.0


def test_levels_and_penalty_cap():
    assert crowd.level(0.0) == "low"
    assert crowd.level(2.0) == "moderate"
    assert crowd.level(4.0) == "high"
    assert crowd.community_penalty(0.0) == 0
    assert crowd.community_penalty(1.0) == 8
    assert crowd.community_penalty(10.0) == crowd.COMMUNITY_PENALTY_CAP


def test_gfw_pressure_mapping():
    assert crowd.gfw_pressure(None)["level"] == "unknown"
    assert crowd.gfw_pressure(4.0) == {"level": "low", "penalty": 0}
    assert crowd.gfw_pressure(20.0)["penalty"] == crowd.GFW_MOD_PENALTY
    assert crowd.gfw_pressure(80.0)["penalty"] == crowd.GFW_HIGH_PENALTY


def test_privacy_no_exact_coords(tmp_path, monkeypatch):
    crowd.record(15.123456, 83.654321, "hotspot", ts=NOW)
    text = json.dumps(json.load(open(tmp_path / "crowd.json")))
    assert "15.123" not in text and "83.654" not in text  # cell index only


def _fake_candidates():
    meta = {"advisory_date": "2026-09-09", "sector_name": "audit"}
    a = {"lat": 15.5, "lon": 83.5, "kind": "pfz", "name": "A",
         "pfz_meta": meta, "chl": None, "dist_km": 18.52}
    b = {"lat": 16.5, "lon": 84.5, "kind": "pfz", "name": "B",
         "pfz_meta": meta, "chl": None, "dist_km": 74.08}
    return [a, b]


def test_voyage_spreads_across_calls(monkeypatch):
    monkeypatch.setattr(voyage, "_pfz_candidates",
                        lambda la, lo, mk, notes: _fake_candidates())
    monkeypatch.setattr(voyage.fc, "get_point_forecast", lambda la, lo: {})
    monkeypatch.setattr(voyage, "_point_state_stub",
                        lambda pf: {"state": "good", "wave_m": 1.0, "why": None})
    monkeypatch.setattr(voyage, "_gfw_pressure", lambda la, lo: None)  # offline

    first = voyage.recommend(15.0, 83.0, max_km=400.0)
    assert first["recommendations"][0]["name"] == "A"          # nearer wins
    assert first["recommendations"][0]["crowd"]["community_recent"] == 0

    # A was recorded → next fisher gets pushed to B (the spread!)
    second = voyage.recommend(15.0, 83.0, max_km=400.0)
    recs = second["recommendations"]
    assert recs[0]["name"] == "B"
    a = next(r for r in recs if r["name"] == "A")
    assert a["score"] < a["score_base"]                        # penalty shown
    assert a["crowd"]["community_recent"] == 1
    assert any("spreading" in s for s in a["reasons"])         # auditable
    assert second["spreading"] is True


# ── B15 GFW burst-resilience ────────────────────────────────────────

def _patch_common(monkeypatch):
    monkeypatch.setattr(voyage, "_pfz_candidates",
                        lambda la, lo, mk, notes: _fake_candidates())
    monkeypatch.setattr(voyage.fc, "get_point_forecast", lambda la, lo: {})
    monkeypatch.setattr(voyage, "_point_state_stub",
                        lambda pf: {"state": "good", "wave_m": 1.0, "why": None})


def test_burst_pause_serves_last_good_no_http(monkeypatch):
    from pipeline import gfw, ttlcache
    _patch_common(monkeypatch)
    ttlcache.remember_last_good(voyage._gfw_cell_key(15.5, 83.5),
                                {"hours": 60.0, "vessel_ids": 4})
    monkeypatch.setattr(gfw, "_rate_limit_remaining", lambda: 50.0)
    monkeypatch.setattr(gfw, "get_fishing_effort",
                        lambda *a, **k: pytest.fail("HTTP fired during burst-pause"))
    out = voyage.recommend(15.0, 83.0, max_km=400.0)
    a = next(r for r in out["recommendations"] if r["name"] == "A")
    assert a["crowd"]["gfw_hours_30d"] == 60.0                   # stale serves
    assert a["crowd"]["gfw_penalty"] == crowd.GFW_HIGH_PENALTY
    assert "last-good" in (a["crowd"]["note"] or "")             # labelled
    b = next(r for r in out["recommendations"] if r["name"] == "B")
    assert b["crowd"]["gfw_hours_30d"] is None                   # honest unknown
    assert any("burst-pause" in n for n in out["notes"])


def test_fresh_success_remembered_for_cell(monkeypatch):
    from pipeline import gfw, ttlcache
    _patch_common(monkeypatch)
    monkeypatch.setattr(gfw, "_rate_limit_remaining", lambda: 0.0)
    monkeypatch.setattr(gfw, "get_fishing_effort",
                        lambda *a, **k: {"hours": 4.0, "vessel_ids": 1})
    out = voyage.recommend(15.0, 83.0, max_km=400.0)
    a = next(r for r in out["recommendations"] if r["name"] == "A")
    assert a["crowd"]["gfw_hours_30d"] == 4.0
    got = ttlcache.get_last_good(voyage._gfw_cell_key(15.5, 83.5), 600)
    assert got is not None and got["hours"] == 4.0               # remembered
