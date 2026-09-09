"""Tests for the chlorophyll fixes (nearest-cell logic + OC-CCI adapter)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from pipeline import erddap_chl, occci_chl


# === NEAREST-CELL LOGIC TESTS (no network) ===
def test_noaa_chl_picks_nearest_cell_not_box_mean():
    """Simulate the Chennai box: 5.14 coastal + 0.28 offshore.
    Nearest-cell to (13.5, 80.5) should be 0.28, not 0.93 mean.
    """
    # Simulate the CSV response from the DINEOF box (5 cells in 0.2° box)
    csv_text = (
        "time,altitude,latitude,longitude,chlor_a\n"
        "2026-08-15T12:00:00Z,0,13.625,80.375,5.14\n"  # coastal NE corner
        "2026-08-15T12:00:00Z,0,13.625,80.625,0.22\n"  # offshore
        "2026-08-15T12:00:00Z,0,13.375,80.375,0.79\n"  # coastal
        "2026-08-15T12:00:00Z,0,13.375,80.625,0.22\n"  # offshore
        "2026-08-15T12:00:00Z,0,13.500,80.500,0.28\n"  # ← exact click
    )
    # Mock _fetch_csv to return this
    orig = erddap_chl._fetch_csv
    erddap_chl._fetch_csv = lambda url: list(
        __import__("csv").DictReader(__import__("io").StringIO(csv_text))
    )
    try:
        result = erddap_chl.get_chlorophyll(13.5, 80.5, "2026-08-15")
        assert result is not None
        assert "value" in result
        # Should pick the cell at (13.5, 80.5) which is 0.28
        assert result["value"] == 0.28, f"expected 0.28, got {result['value']}"
        # Box mean would be 1.33, but we should NOT use it
        assert result.get("box_mean", 0) > 1.0  # box stats still reported
        print(f"✅ test_noaa_chl_picks_nearest_cell_not_box_mean passed (value={result['value']}, box_mean={result.get('box_mean')})")
    finally:
        erddap_chl._fetch_csv = orig


def test_noaa_chl_handles_no_data():
    """Empty / cloud-covered response returns error dict, not crash."""
    orig = erddap_chl._fetch_csv
    erddap_chl._fetch_csv = lambda url: []
    try:
        result = erddap_chl.get_chlorophyll(13.5, 80.5, "2026-08-15")
        assert result is not None
        assert "error" in result or result.get("value") is None
        print("✅ test_noaa_chl_handles_no_data passed")
    finally:
        erddap_chl._fetch_csv = orig


# === OC-CCI ADAPTER TESTS ===
def test_occci_query_url_2d():
    """OC-CCI is 2D (no altitude axis), order is time, lat, lon."""
    url = occci_chl.build_query_url(13.5, 80.5, "2026-08-15", radius_deg=0.05)
    # Should NOT contain altitude
    assert "altitude" not in url
    assert "13.4500" in url or "13.45" in url
    assert "80.4500" in url or "80.45" in url
    print(f"✅ test_occci_query_url_2d passed (url={url[:80]}...)")


def test_occci_picks_nearest_cell():
    """OC-CCI nearest-cell from a 0.1° box JSON response."""
    fake_json = {
        "table": {
            "columnNames": ["time", "latitude", "longitude", "chlor_a"],
            "rows": [
                ["2026-08-16T00:00:00Z", 13.55, 80.45, 0.49],
                ["2026-08-16T00:00:00Z", 13.55, 80.55, 0.31],
                ["2026-08-16T00:00:00Z", 13.45, 80.45, 0.85],
                ["2026-08-16T00:00:00Z", 13.45, 80.55, 0.16],
            ]
        }
    }
    # Mock urllib to return this JSON
    import urllib.request
    orig_urlopen = urllib.request.urlopen
    class FakeResp:
        def __init__(self, data): self.data = data
        def read(self): return json.dumps(self.data).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): pass
    def fake_urlopen(req, timeout=15):
        return FakeResp(fake_json)
    urllib.request.urlopen = fake_urlopen
    try:
        result = occci_chl.get_chlorophyll(13.5, 80.5, "2026-08-15")
        assert result is not None
        # Nearest cell to (13.5, 80.5) is (13.55, 80.55) at 0.31
        # (distance 0.0707 vs 13.45, 80.55 at 0.0707 — same distance,
        # but we'll pick whichever comes first in the loop)
        assert "value" in result
        assert result["value"] in (0.31, 0.49)  # either of the two nearest
        assert "ESA OC-CCI" in result["source"]
        print(f"✅ test_occci_picks_nearest_cell passed (value={result['value']})")
    finally:
        urllib.request.urlopen = orig_urlopen


def test_occci_handles_all_null():
    """All null (clouds) → error dict, not crash."""
    fake_json = {
        "table": {
            "columnNames": ["time", "latitude", "longitude", "chlor_a"],
            "rows": [
                ["2026-08-16T00:00:00Z", 13.5, 80.5, None],
                ["2026-08-16T00:00:00Z", 13.6, 80.5, None],
            ]
        }
    }
    import urllib.request
    class FakeResp:
        def __init__(self, data): self.data = data
        def read(self): return json.dumps(self.data).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *a): pass
    urllib.request.urlopen = lambda req, timeout=15: FakeResp(fake_json)
    result = occci_chl.get_chlorophyll(13.5, 80.5, "2026-08-15")
    assert result is not None
    assert "error" in result
    print("✅ test_occci_handles_all_null passed")


if __name__ == "__main__":
    test_noaa_chl_picks_nearest_cell_not_box_mean()
    test_noaa_chl_handles_no_data()
    test_occci_query_url_2d()
    test_occci_picks_nearest_cell()
    test_occci_handles_all_null()
    print("\n🎉 All 5 chlorophyll fix tests passed!")
