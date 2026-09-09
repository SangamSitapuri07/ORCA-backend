"""Tests for the 3 newly added agents: weather, gis, anomaly (offline)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.agents import weather, gis, anomaly, run_all


def make_snap(**overrides):
    snap = {
        "lat": 13.5, "lon": 80.5, "date": "2026-08-15",
        "fetched_at": "2026-08-15T12:00:00+00:00",
        "sst_max": 29.6, "sst_min": 28.1, "sst_mean": 29.0,
        "wave_max": 3.2, "wave_mean": 2.32,
        "chlorophyll": 1.0, "chlorophyll_unit": "mg/m^3",
        "chlorophyll_source": "NOAA",
        "fishing_hours": 5.0, "vessel_count": 5,
        "fleet_by_flag": {"IND": 5}, "fleet_by_gear": {"trawler": 5},
        "pfz_score": 0.5,
        "data_sources_used": ["Open-Meteo", "NOAA"],
        "data_sources_failed": [],
    }
    snap.update(overrides)
    return snap


# ── Agent 3: Weather (mocked) ──

def test_weather_no_location():
    r = weather.analyze({"lat": None, "lon": None, "date": None})
    assert r["agent"] == "weather"
    assert r["risk_level"] == "unknown"
    print("✅ test_weather_no_location passed")


def test_weather_api_error(monkeypatch=None):
    # Mock _fetch to simulate API failure
    original = weather._fetch
    weather._fetch = lambda *a, **kw: (_ for _ in ()).throw(
        Exception("simulated network error")
    )
    try:
        r = weather.analyze(make_snap())
        assert r["risk_level"] == "unknown"
        assert "unreachable" in r["summary"].lower() or "unavailable" in r["summary"].lower()
    finally:
        weather._fetch = original
    print("✅ test_weather_api_error passed")


def test_weather_good_conditions():
    # Mock _fetch to return calm weather
    original = weather._fetch
    weather._fetch = lambda *a, **kw: {
        "daily": {
            "wind_speed_10m_max": [5.0],
            "wind_gusts_10m_max": [7.0],
            "precipitation_sum": [0.0],
            "weather_code": [1],
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [25.0],
        }
    }
    try:
        r = weather.analyze(make_snap())
        assert r["risk_level"] == "low"
        types = [f["type"] for f in r["findings"]]
        assert "wind_calm" in types
    finally:
        weather._fetch = original
    print("✅ test_weather_good_conditions passed")


def test_weather_storm_warning():
    original = weather._fetch
    weather._fetch = lambda *a, **kw: {
        "daily": {
            "wind_speed_10m_max": [25.0],
            "wind_gusts_10m_max": [30.0],
            "precipitation_sum": [50.0],
            "weather_code": [95],
            "temperature_2m_max": [28.0],
            "temperature_2m_min": [24.0],
        }
    }
    try:
        r = weather.analyze(make_snap())
        assert r["risk_level"] == "high"
        types = [f["type"] for f in r["findings"]]
        assert "storm_warning" in types
    finally:
        weather._fetch = original
    print("✅ test_weather_storm_warning passed")


# ── Agent 4: GIS (no network needed) ──

def test_gis_in_indian_eez():
    r = gis.analyze(make_snap(lat=19.0, lon=72.8))  # Mumbai
    assert r["agent"] == "gis"
    types = [f["type"] for f in r["findings"]]
    assert "in_indian_eez" in types
    print("✅ test_gis_in_indian_eez passed")


def test_gis_outside_eez():
    r = gis.analyze(make_snap(lat=10.0, lon=60.0))  # Arabian Sea
    assert r["risk_level"] in ("low", "moderate")
    types = [f["type"] for f in r["findings"]]
    assert "outside_indian_eez" in types
    print("✅ test_gis_outside_eez passed")


def test_gis_nearest_ports():
    r = gis.analyze(make_snap(lat=19.0, lon=72.8))  # Mumbai
    types = [f["type"] for f in r["findings"]]
    assert "nearest_ports" in types
    # Should find Mumbai ports
    port_finding = next(f for f in r["findings"] if f["type"] == "nearest_ports")
    assert "Mumbai" in port_finding["msg"]
    print("✅ test_gis_nearest_ports passed")


def test_gis_mpa_overlap():
    r = gis.analyze(make_snap(lat=9.25, lon=79.30))  # Gulf of Mannar MNP
    types = [f["type"] for f in r["findings"]]
    assert "in_marine_protected_area" in types
    assert r["risk_level"] == "moderate"
    print("✅ test_gis_mpa_overlap passed")


def test_gis_no_location():
    r = gis.analyze({"lat": None, "lon": None})
    assert r["risk_level"] == "unknown"
    print("✅ test_gis_no_location passed")


# ── Agent 8: Anomaly (mocked) ──

def test_anomaly_no_location():
    r = anomaly.analyze({"lat": None, "lon": None, "date": None})
    assert r["risk_level"] == "unknown"
    print("✅ test_anomaly_no_location passed")


def test_anomaly_api_failure():
    original = anomaly._fetch_baseline
    anomaly._fetch_baseline = lambda *a, **kw: (_ for _ in ()).throw(
        Exception("simulated network")
    )
    try:
        r = anomaly.analyze(make_snap())
        assert r["risk_level"] == "unknown"
    finally:
        anomaly._fetch_baseline = original
    print("✅ test_anomaly_api_failure passed")


def test_anomaly_no_baseline():
    original = anomaly._fetch_baseline
    anomaly._fetch_baseline = lambda *a, **kw: {}
    try:
        r = anomaly.analyze(make_snap())
        assert r["risk_level"] == "unknown"
    finally:
        anomaly._fetch_baseline = original
    print("✅ test_anomaly_no_baseline passed")


def test_anomaly_normal_range():
    original = anomaly._fetch_baseline
    anomaly._fetch_baseline = lambda *a, **kw: {
        "baseline_sst_mean": 29.0,  # current is 29.0 → delta 0
        "baseline_sst_n": 5,
        "baseline_wave_mean": 2.5,  # current is 3.2 → ratio 1.28
    }
    try:
        r = anomaly.analyze(make_snap(sst_mean=29.0, wave_max=3.2))
        assert r["risk_level"] == "low"
        types = [f["type"] for f in r["findings"]]
        assert "sst_anomaly" in types
    finally:
        anomaly._fetch_baseline = original
    print("✅ test_anomaly_normal_range passed")


def test_anomaly_marine_heatwave():
    original = anomaly._fetch_baseline
    anomaly._fetch_baseline = lambda *a, **kw: {
        "baseline_sst_mean": 27.0,  # current is 30.5 → delta 3.5 → extreme
        "baseline_sst_n": 5,
        "baseline_wave_mean": 2.0,
    }
    try:
        r = anomaly.analyze(make_snap(sst_mean=30.5, wave_max=3.0))
        assert r["risk_level"] == "high"
        # Find the SST anomaly finding
        sst_findings = [f for f in r["findings"] if f["type"] == "sst_anomaly"]
        assert sst_findings
        assert "EXTREME" in sst_findings[0]["msg"]
    finally:
        anomaly._fetch_baseline = original
    print("✅ test_anomaly_marine_heatwave passed")


# ── Integration: all 9 agents in one pipeline ──

def test_all_9_agents_in_pipeline():
    """Mock all network calls and verify the full pipeline runs 9 agents."""
    weather._fetch = lambda *a, **kw: {
        "daily": {
            "wind_speed_10m_max": [5.0],
            "wind_gusts_10m_max": [7.0],
            "precipitation_sum": [0.0],
            "weather_code": [1],
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [25.0],
        }
    }
    anomaly._fetch_baseline = lambda *a, **kw: {
        "baseline_sst_mean": 28.0,
        "baseline_sst_n": 5,
        "baseline_wave_mean": 2.5,
    }
    snap = make_snap()
    results = run_all(snap)
    assert len(results) == 9, f"Expected 9 agents, got {len(results)}"
    names = [r["agent"] for r in results]
    expected = {"ocean", "satellite", "weather", "gis", "fisheries",
                "marine_ecology", "marine_risk", "anomaly", "validation"}
    assert set(names) == expected, f"Missing/extra agents: {set(names) ^ expected}"
    print(f"✅ test_all_9_agents_in_pipeline passed ({len(results)} agents)")


if __name__ == "__main__":
    test_weather_no_location()
    test_weather_api_error()
    test_weather_good_conditions()
    test_weather_storm_warning()
    test_gis_in_indian_eez()
    test_gis_outside_eez()
    test_gis_nearest_ports()
    test_gis_mpa_overlap()
    test_gis_no_location()
    test_anomaly_no_location()
    test_anomaly_api_failure()
    test_anomaly_no_baseline()
    test_anomaly_normal_range()
    test_anomaly_marine_heatwave()
    test_all_9_agents_in_pipeline()
    print("\n🎉 All 15 new agent tests passed!")
