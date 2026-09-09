"""Smoke tests for the FastAPI backend. Run while the server is up:

  python -m uvicorn backend.main:app --port 8000 &
  python backend/test_api.py
"""
import sys
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000"


def get(path, params=None):
    url = f"{BASE}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    try:
        # Cold-tap multi-source fetches (NOAA + OC-CCI + INCOIS + Open-Meteo,
        # with lag-retry) can take ~90 s before the 10-min cache fills.
        with urllib.request.urlopen(url, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body[:200]}")
        raise


def test_root():
    r = get("/")
    assert r["service"].startswith("ORCA")
    assert "/api/v1/reason" in r["endpoints"]
    print("✅ test_root passed")


def test_health():
    r = get("/api/v1/health")
    assert r["status"] == "ok"
    assert "data_sources" in r
    print(f"✅ test_health passed (gfw_token={r['gfw_token_configured']})")


def test_zones():
    r = get("/api/v1/zones")
    assert r["count"] == 8
    assert r["zones"][0]["name"].startswith("Mumbai")
    print(f"✅ test_zones passed ({r['count']} zones)")


def test_datasets():
    r = get("/api/v1/datasets")
    assert len(r["sources"]) >= 5
    assert len(r["agents"]) == 10
    implemented = sum(1 for a in r["agents"] if a["implemented"])
    print(f"✅ test_datasets passed ({len(r['sources'])} sources, {implemented}/{len(r['agents'])} agents implemented)")


def test_zone():
    r = get("/api/v1/zone", {"lat": 19.0, "lon": 72.8, "include_gfw": "false"})
    assert r["lat"] == 19.0
    assert r["lon"] == 72.8
    assert "data_sources_used" in r
    assert "data_sources_failed" in r
    print(f"✅ test_zone passed (data_sources_used={len(r.get('data_sources_used', []))})")


def test_zone_invalid_date():
    try:
        get("/api/v1/zone", {"lat": 19, "lon": 72.8, "date": "not-a-date"})
        print("❌ test_zone_invalid_date FAILED - should have raised 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400
        print("✅ test_zone_invalid_date passed (rejected 400)")


def test_grid_basic():
    r = get("/api/v1/grid", {"min_lat": 18, "max_lat": 19, "min_lon": 72, "max_lon": 73, "step_deg": 1.0, "include_gfw": "false"})
    assert r["n_points"] == 4
    assert len(r["points"]) == 4
    print(f"✅ test_grid_basic passed ({r['n_points']} points)")


def test_grid_too_large():
    try:
        get("/api/v1/grid", {"min_lat": 0, "max_lat": 50, "min_lon": 0, "max_lon": 50, "step_deg": 0.5, "include_gfw": "true"})
        print("❌ test_grid_too_large FAILED - should have raised 400")
    except urllib.error.HTTPError as e:
        assert e.code == 400
        print("✅ test_grid_too_large passed (rejected 400)")


def test_reason_full():
    r = get("/api/v1/reason", {"lat": 19.0, "lon": 72.8, "include_gfw": "false"})
    assert "overall_risk" in r
    assert "recommendation" in r
    assert "summary" in r
    assert "agents" in r
    assert "snapshot" in r
    print(f"✅ test_reason_full passed (overall_risk={r['overall_risk']}, {len(r['agents'])} agents)")


def test_reason_select_agents():
    r = get("/api/v1/reason", {"lat": 19, "lon": 72.8, "include_gfw": "false", "agents": "ocean,fisheries"})
    assert len(r["agents"]) == 2
    agent_names = {a["agent"] for a in r["agents"]}
    assert agent_names == {"ocean", "fisheries"}
    print(f"✅ test_reason_select_agents passed ({agent_names})")


if __name__ == "__main__":
    test_root()
    test_health()
    test_zones()
    test_datasets()
    test_zone()
    test_zone_invalid_date()
    test_grid_basic()
    test_grid_too_large()
    test_reason_full()
    test_reason_select_agents()
    print("\n🎉 All 10 API tests passed!")
