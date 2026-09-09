"""Tests for the agent system (offline, no API calls)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.agents import ocean, satellite, fisheries, marine_ecology, marine_risk, validation, run_all
from pipeline.reasoner import reason


def make_snap(**overrides):
    snap = {
        "lat": 19.0, "lon": 72.8, "date": "2026-08-15",
        "fetched_at": "2026-08-15T12:00:00+00:00",
        "sst_max": 29.6, "sst_min": 28.1, "sst_mean": 29.0,
        "wave_max": 3.2, "wave_mean": 2.32,
        "chlorophyll": 3.95, "chlorophyll_unit": "mg/m^3",
        "chlorophyll_source": "NOAA ERDDAP",
        "fishing_hours": 1.0, "vessel_count": 2,
        "fleet_by_flag": {"IND": 2}, "fleet_by_gear": {"trawlers": 1, "inconclusive": 1},
        "pfz_score": 0.68,
        "data_sources_used": ["Open-Meteo", "NOAA", "GFW"],
        "data_sources_failed": [],
    }
    snap.update(overrides)
    return snap


# ── Agent 1: Ocean ──

def test_ocean_optimal_sst():
    snap = make_snap(sst_mean=27.0, sst_max=27.5, sst_min=26.5, wave_max=1.0)
    r = ocean.analyze(snap)
    assert r["agent"] == "ocean"
    assert r["risk_level"] == "low"
    types = [f["type"] for f in r["findings"]]
    assert "sst_optimal" in types
    assert "wave_calm" in types
    print("✅ test_ocean_optimal_sst passed")


def test_ocean_high_waves():
    snap = make_snap(wave_max=4.5, wave_mean=3.0)
    r = ocean.analyze(snap)
    assert r["risk_level"] == "high"
    types = [f["type"] for f in r["findings"]]
    assert "wave_warning_high" in types
    print("✅ test_ocean_high_waves passed")


def test_ocean_sst_front():
    snap = make_snap(sst_max=29.0, sst_min=26.5, sst_mean=27.75)  # swing 2.5°C
    r = ocean.analyze(snap)
    types = [f["type"] for f in r["findings"]]
    assert "sst_front" in types
    print("✅ test_ocean_sst_front passed")


# ── Agent 2: Satellite ──

def test_satellite_productive():
    snap = make_snap(chlorophyll=1.2)
    r = satellite.analyze(snap)
    assert r["risk_level"] == "low"
    types = [f["type"] for f in r["findings"]]
    assert "chl_productive" in types
    print("✅ test_satellite_productive passed")


def test_satellite_bloom_warning():
    snap = make_snap(chlorophyll=8.0)
    r = satellite.analyze(snap)
    assert r["risk_level"] == "moderate"
    types = [f["type"] for f in r["findings"]]
    assert "chl_bloom" in types
    print("✅ test_satellite_bloom_warning passed")


def test_satellite_no_data():
    snap = make_snap(chlorophyll=None, chlorophyll_source=None)
    r = satellite.analyze(snap)
    types = [f["type"] for f in r["findings"]]
    assert "no_chlorophyll_data" in types
    assert r["risk_level"] == "unknown"
    print("✅ test_satellite_no_data passed")


# ── Agent 6: Fisheries ──

def test_fisheries_highly_recommended():
    snap = make_snap(chlorophyll=1.0, sst_mean=27.0, fishing_hours=80.0, pfz_score=0.85)
    r = fisheries.analyze(snap)
    assert r["verdict"] == "highly_recommended"
    assert r["risk_level"] == "low"
    types = [f["type"] for f in r["findings"]]
    assert "pfz_verdict" in types
    assert "chl_pfz_sweet_spot" in types
    assert "sst_pelagic_optimal" in types
    assert "high_fishing_activity" in types
    print("✅ test_fisheries_highly_recommended passed")


def test_fisheries_not_recommended():
    snap = make_snap(chlorophyll=0.05, sst_mean=32.0, fishing_hours=0, pfz_score=0.1)
    r = fisheries.analyze(snap)
    assert r["verdict"] == "not_recommended"
    assert r["risk_level"] == "high"
    print("✅ test_fisheries_not_recommended passed")


# ── Agent 5: Marine Ecology ──

def test_ecology_upwelling():
    snap = make_snap(chl=3.0, sst_mean=24.0)  # cold + high chl = upwelling
    r = marine_ecology.analyze(snap)
    types = [f["type"] for f in r["findings"]]
    assert "upwelling_signature" in types
    print("✅ test_ecology_upwelling passed")


def test_ecology_validated_fishing():
    snap = make_snap(chl=1.5, sst_mean=28.0, fishing_hours=50.0)
    r = marine_ecology.analyze(snap)
    types = [f["type"] for f in r["findings"]]
    assert "validated_fishing_ground" in types
    print("✅ test_ecology_validated_fishing passed")


# ── Agent 7: Marine Risk ──

def test_risk_low_when_all_good():
    snap = make_snap(wave_max=1.0)
    agents = run_all(snap)
    r = marine_risk.analyze(snap, agent_results=agents)
    assert r["risk_level"] == "low"
    print("✅ test_risk_low_when_all_good passed")


def test_risk_high_when_waves_high():
    snap = make_snap(wave_max=4.5)
    agents = run_all(snap)
    r = marine_risk.analyze(snap, agent_results=agents)
    assert r["risk_level"] in ("high", "critical")
    print("✅ test_risk_high_when_waves_high passed")


# ── Agent 9: Validation ──

def test_validation_clean():
    snap = make_snap()
    r = validation.analyze(snap)
    assert r["risk_level"] == "low"
    assert r["findings"] == []
    print("✅ test_validation_clean passed")


def test_validation_all_failed():
    snap = make_snap(
        data_sources_used=[],
        data_sources_failed=["X", "Y", "Z", "W"],
    )
    r = validation.analyze(snap)
    assert r["risk_level"] == "high"
    types = [f["type"] for f in r["findings"]]
    assert "all_sources_failed" in types
    print("✅ test_validation_all_failed passed")


def test_validation_chl_out_of_range():
    snap = make_snap(chlorophyll=200.0)
    r = validation.analyze(snap)
    assert r["risk_level"] == "high"
    types = [f["type"] for f in r["findings"]]
    assert "chl_out_of_range" in types
    print("✅ test_validation_chl_out_of_range passed")


# ── Reasoner ──

def test_reasoner_full_pipeline():
    snap = make_snap()
    out = reason(snap)
    assert "zone" in out
    assert "agents" in out
    assert "overall_risk" in out
    assert "summary" in out
    assert "recommendation" in out
    assert len(out["agents"]) == 9
    agent_names = [a["agent"] for a in out["agents"]]
    assert "ocean" in agent_names
    assert "satellite" in agent_names
    assert "weather" in agent_names
    assert "gis" in agent_names
    assert "fisheries" in agent_names
    assert "marine_ecology" in agent_names
    assert "marine_risk" in agent_names
    assert "anomaly" in agent_names
    assert "validation" in agent_names
    print(f"✅ test_reasoner_full_pipeline passed (overall_risk={out['overall_risk']})")


def test_reasoner_select_agents():
    snap = make_snap()
    out = reason(snap, include_agents=["ocean", "fisheries"])
    assert len(out["agents"]) == 2
    assert {a["agent"] for a in out["agents"]} == {"ocean", "fisheries"}
    print("✅ test_reasoner_select_agents passed")


if __name__ == "__main__":
    test_ocean_optimal_sst()
    test_ocean_high_waves()
    test_ocean_sst_front()
    test_satellite_productive()
    test_satellite_bloom_warning()
    test_satellite_no_data()
    test_fisheries_highly_recommended()
    test_fisheries_not_recommended()
    test_ecology_upwelling()
    test_ecology_validated_fishing()
    test_risk_low_when_all_good()
    test_risk_high_when_waves_high()
    test_validation_clean()
    test_validation_all_failed()
    test_validation_chl_out_of_range()
    test_reasoner_full_pipeline()
    test_reasoner_select_agents()
    print("\n🎉 All 17 agent + reasoner tests passed!")
