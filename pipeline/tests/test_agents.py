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
        "fishing_window_start": "2026-07-12", "fishing_window_end": "2026-08-11",
        "fishing_bbox_radius_deg": 0.5,
        "data_sources_used": ["Open-Meteo", "NOAA", "GFW"],
        "data_sources_failed": [],
    }
    snap.update(overrides)
    return snap


# ── Agent 1: Ocean ──

def test_ocean_complete_wave_forecast_below_threshold():
    snap = make_snap(
        sst_mean=27.0, sst_max=27.5, sst_min=26.5, wave_max=1.0,
        wave_now_m=0.8, wave_peak_48h_m=1.0,
    )
    result = ocean.analyze(snap)
    assert result["agent"] == "ocean"
    assert result["risk_level"] == "low"
    types = [finding["type"] for finding in result["findings"]]
    assert "sst_observation" in types
    assert "wave_calm" in types
    print("✅ test_ocean_complete_wave_forecast_below_threshold passed")


def test_ocean_high_waves():
    snap = make_snap(wave_max=4.5, wave_mean=3.0, wave_now_m=4.1, wave_peak_48h_m=4.5)
    r = ocean.analyze(snap)
    assert r["risk_level"] == "high"
    types = [f["type"] for f in r["findings"]]
    assert "wave_warning_high" in types
    print("✅ test_ocean_high_waves passed")


def test_ocean_sst_window_range_is_not_called_a_front():
    snap = make_snap(sst_max=29.0, sst_min=26.5, sst_mean=27.75)
    result = ocean.analyze(snap)
    types = [finding["type"] for finding in result["findings"]]
    assert "sst_window_range" in types
    assert "sst_front" not in types
    print("✅ test_ocean_sst_window_range_is_not_called_a_front passed")


# ── Agent 2: Satellite ──

def test_satellite_chlorophyll_is_context_only():
    result = satellite.analyze(make_snap(chlorophyll=1.2))
    assert result["risk_level"] == "unknown"
    assert result["status"] == "context_only"
    assert any(f["type"] == "chlorophyll_observation" for f in result["findings"])
    print("✅ test_satellite_chlorophyll_is_context_only passed")


def test_satellite_high_chlorophyll_is_not_hab_warning():
    result = satellite.analyze(make_snap(chlorophyll=8.0))
    assert result["risk_level"] == "unknown"
    blob = " ".join(f["msg"] for f in result["findings"])
    assert "possible harmful" not in blob.lower()
    assert "does not identify HABs" in blob
    print("✅ test_satellite_high_chlorophyll_is_not_hab_warning passed")


def test_satellite_no_data():
    snap = make_snap(chlorophyll=None, chlorophyll_source=None)
    r = satellite.analyze(snap)
    types = [f["type"] for f in r["findings"]]
    assert "no_chlorophyll_data" in types
    assert r["risk_level"] == "unknown"
    print("✅ test_satellite_no_data passed")


# ── Agent 6: Fisheries ──

def test_fisheries_reports_context_without_pfz_verdict():
    snap = make_snap(chlorophyll=1.0, sst_mean=27.0, fishing_hours=80.0)
    r = fisheries.analyze(snap)
    assert r["verdict"] == "unavailable"
    assert r["risk_level"] == "unknown"
    types = [f["type"] for f in r["findings"]]
    assert "chlorophyll_observation" in types
    assert "sst_observation" in types
    assert "gfw_fishing_activity" in types
    assert "official_pfz_not_evaluated" in types
    assert "pfz_verdict" not in types
    gfw = next(f for f in r["findings"] if f["type"] == "gfw_fishing_activity")
    assert gfw["window_start"] == "2026-07-12"
    assert "does not establish catch" in gfw["msg"]
    print("✅ test_fisheries_reports_context_without_pfz_verdict passed")


def test_fisheries_never_converts_values_to_negative_recommendation():
    snap = make_snap(chlorophyll=0.05, sst_mean=32.0, fishing_hours=0)
    r = fisheries.analyze(snap)
    assert r["verdict"] == "unavailable"
    assert r["risk_level"] == "unknown"
    assert all(f["type"] != "pfz_verdict" for f in r["findings"])
    print("✅ test_fisheries_never_converts_values_to_negative_recommendation passed")


# ── Agent 5: Marine Ecology ──

def test_ecology_does_not_diagnose_upwelling_or_hab():
    snap = make_snap(chlorophyll=8.0, sst_mean=30.0)
    r = marine_ecology.analyze(snap)
    types = [f["type"] for f in r["findings"]]
    assert types == ["sst_chlorophyll_coobservation", "chlorophyll_gfw_coobservation"]
    assert r["risk_level"] == "unknown"
    assert "does not establish upwelling" in r["findings"][0]["msg"]
    print("✅ test_ecology_does_not_diagnose_upwelling_or_hab passed")


def test_ecology_does_not_call_activity_a_proven_fishing_ground():
    snap = make_snap(chlorophyll=1.5, sst_mean=28.0, fishing_hours=50.0)
    r = marine_ecology.analyze(snap)
    finding = next(f for f in r["findings"] if f["type"] == "chlorophyll_gfw_coobservation")
    assert "does not prove catch" in finding["msg"]
    assert "validated_fishing_ground" not in [f["type"] for f in r["findings"]]
    print("✅ test_ecology_does_not_call_activity_a_proven_fishing_ground passed")


# ── Agent 7: Marine Risk ──

def test_risk_low_when_complete_evidence_is_below_threshold():
    snap = make_snap(wave_now_m=0.8, wave_peak_48h_m=1.0)
    ocean_result = ocean.analyze(snap)
    weather_result = {"agent": "weather", "findings": [], "risk_level": "low", "evidence": {"complete": True}}
    result = marine_risk.analyze(snap, agent_results=[ocean_result, weather_result])
    assert result["risk_level"] == "low"
    print("✅ test_risk_low_when_complete_evidence_is_below_threshold passed")


def test_risk_high_when_waves_high():
    snap = make_snap(wave_now_m=4.1, wave_peak_48h_m=4.5)
    ocean_result = ocean.analyze(snap)
    result = marine_risk.analyze(snap, agent_results=[ocean_result])
    assert result["risk_level"] in ("high", "critical")
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
    assert len(out["agents"]) == 11
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
    test_ocean_complete_wave_forecast_below_threshold()
    test_ocean_high_waves()
    test_ocean_sst_window_range_is_not_called_a_front()
    test_satellite_chlorophyll_is_context_only()
    test_satellite_high_chlorophyll_is_not_hab_warning()
    test_satellite_no_data()
    test_fisheries_reports_context_without_pfz_verdict()
    test_fisheries_never_converts_values_to_negative_recommendation()
    test_ecology_does_not_diagnose_upwelling_or_hab()
    test_ecology_does_not_call_activity_a_proven_fishing_ground()
    test_risk_low_when_complete_evidence_is_below_threshold()
    test_risk_high_when_waves_high()
    test_validation_clean()
    test_validation_all_failed()
    test_validation_chl_out_of_range()
    test_reasoner_full_pipeline()
    test_reasoner_select_agents()
    print("\n🎉 All 17 agent + reasoner tests passed!")
