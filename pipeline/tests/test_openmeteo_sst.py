"""Tests for Open-Meteo SST adapter (live calls — no key required)."""
import pytest
from pipeline.tests.conftest import requires_network
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline import openmeteo_sst as om


@pytest.mark.live
@requires_network
def test_single_point_live():
    """Hit the real Open-Meteo API. They don't require a key."""
    r = om.get_sst_at_point(19.0, 72.8, "2026-08-01", "2026-08-30")
    assert r is not None
    assert "error" not in r, f"API error: {r}"
    assert r["sst_max"] is not None and 20 < r["sst_max"] < 35, f"Bad SST: {r['sst_max']}"
    assert r["sst_min"] is not None and 20 < r["sst_min"] < 35
    assert r["sst_mean"] is not None
    assert r["wave_max"] is not None and 0 < r["wave_max"] < 10
    assert r["n_days"] == 30
    assert r["source"].startswith("Open-Meteo")
    assert len(r["daily"]) == 30
    print(f"✅ test_single_point_live passed (SST {r['sst_min']}-{r['sst_max']}°C, "
          f"wave max {r['wave_max']}m)")


@pytest.mark.live
@requires_network
def test_grid_live():
    """Hit the grid endpoint with a small 2°×2° at 0.5° step = 25 points."""
    r = om.get_sst_grid(18.0, 20.0, 72.0, 74.0, "2026-08-01", "2026-08-30", step_deg=0.5)
    assert r is not None
    assert "error" not in r, f"API error: {r}"
    assert r["n_points"] == 25, f"Expected 25 points (5×5), got {r['n_points']}"
    for p in r["points"]:
        assert "sst_max" in p
        assert "sst_min" in p
        assert "sst_mean" in p
        assert "wave_max" in p
    sst_range = [p["sst_max"] for p in r["points"] if p["sst_max"] is not None]
    assert max(sst_range) - min(sst_range) < 3.0, "SST should be relatively uniform over 2°×2°"
    print(f"✅ test_grid_live passed (25 points, SST range {min(sst_range):.1f}-{max(sst_range):.1f}°C)")


def test_grid_too_dense():
    """Reject grid that would ask for too many points."""
    r = om.get_sst_grid(0.0, 5.0, 70.0, 75.0, "2026-08-01", "2026-08-07", step_deg=0.05)
    assert r is not None
    assert "error" in r
    assert "too dense" in r["error"].lower()
    print("✅ test_grid_too_dense passed (rejected 5000+ point grid)")


@pytest.mark.live
@requires_network
def test_demo_indian_ocean():
    """Run the curated demo points and check we get something for Mumbai."""
    results = om.demo_indian_ocean_sst("2026-08-01", "2026-08-30")
    assert len(results) == 8, f"Expected 8 demo points, got {len(results)}"
    mumbai = next((r for r in results if r["name"] == "Mumbai offshore"), None)
    assert mumbai is not None
    assert "error" not in mumbai
    assert mumbai["sst_max"] is not None
    # Coastal SSTs in Aug 2026 should be 27-32°C
    assert 26 < mumbai["sst_max"] < 33
    print(f"✅ test_demo_indian_ocean passed (Mumbai SST: {mumbai['sst_min']}-{mumbai['sst_max']}°C)")


if __name__ == "__main__":
    test_single_point_live()
    test_grid_live()
    test_grid_too_dense()
    test_demo_indian_ocean()
    print("\n🎉 All 4 Open-Meteo tests passed!")
