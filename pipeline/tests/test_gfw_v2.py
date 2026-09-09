"""Tests for GFW adapter response parsing (no token required)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline import gfw


def test_gfw_parse_total_field():
    """GFW returns {'total': float, 'entries': [...]} — make sure we read 'total'."""
    gfw._make_request = lambda *a, **kw: {
        "total": 497.88,
        "entries": [
            {"date": "2026-05-06", "vesselIDs": ["v1", "v2", "v3"], "hours": 12.4},
            {"date": "2026-05-07", "vesselIDs": ["v2", "v3", "v4"], "hours": 15.0},
        ],
    }
    r = gfw.get_fishing_effort(19.0, 72.8, "2026-05-01", "2026-06-01", token="dummy")
    assert r is not None
    assert r["hours"] == 497.88, f"Expected 497.88 from 'total' field, got {r['hours']}"
    assert r["vessel_ids"] == 4, f"Expected 4 unique vessels, got {r['vessel_ids']}"
    assert sorted(r["vessel_id_sample"]) == ["v1", "v2", "v3"]
    print("✅ test_gfw_parse_total_field passed")


def test_gfw_parse_grouped_by_dataset():
    """Older format: entries: [{dataset_key: [{date, hours, vesselIDs}]}]"""
    gfw._make_request = lambda *a, **kw: {
        "entries": [
            {
                "public-global-fishing-effort:latest": [
                    {"date": "2026-05-06", "vesselIDs": ["a", "b"], "hours": 10.0},
                    {"date": "2026-05-07", "vesselIDs": ["b", "c"], "hours": 8.0},
                ]
            }
        ]
    }
    r = gfw.get_fishing_effort(10.0, 70.0, "2026-05-01", "2026-06-01", token="dummy")
    assert r is not None
    assert r["vessel_ids"] == 3
    print("✅ test_gfw_parse_grouped_by_dataset passed")


def test_gfw_no_token():
    r = gfw.get_fishing_effort(0, 0, "2026-05-01", "2026-06-01", token=None)
    assert r is not None
    assert "error" in r
    assert "GFW_API_TOKEN" in r["error"]
    print("✅ test_gfw_no_token passed")


def test_gfw_vessels_in_region_by_flag():
    gfw._make_request = lambda *a, **kw: {
        "total": 100.0,
        "entries": [
            {"date": "2026-05-06", "vesselIDs": ["v1", "v2"], "flag": "IND", "geartype": "trawler", "hours": 50.0},
            {"date": "2026-05-07", "vesselIDs": ["v3"], "flag": "LKA", "geartype": "gillnetter", "hours": 50.0},
        ]
    }
    r = gfw.get_fishing_vessels_in_region(19.0, 72.8, token="dummy")
    assert r is not None
    assert r["vessel_count"] == 3
    assert r["by_flag"] == {"IND": 2, "LKA": 1}
    assert r["by_gear"] == {"trawler": 2, "gillnetter": 1}
    print("✅ test_gfw_vessels_in_region_by_flag passed")


def test_gfw_vessels_in_region_grouped():
    """Grouped response: [{dataset_key: [...]}]"""
    gfw._make_request = lambda *a, **kw: {
        "entries": [
            {
                "public-global-fishing-effort:latest": [
                    {"date": "2026-05-06", "vesselIDs": ["v1"], "flag": "IND", "geartype": "trawler"},
                    {"date": "2026-05-07", "vesselIDs": ["v2"], "flag": "IND", "geartype": "trawler"},
                ]
            }
        ]
    }
    r = gfw.get_fishing_vessels_in_region(19.0, 72.8, token="dummy")
    assert r is not None
    assert r["vessel_count"] == 2
    assert r["by_flag"] == {"IND": 2}
    print("✅ test_gfw_vessels_in_region_grouped passed")


def test_gfw_date_clamp():
    start, end = gfw._clamp_date_range("2020-01-01", "2020-01-31")
    from datetime import date
    today = date.today()
    earliest = today.toordinal() - 90
    assert date.fromisoformat(end).toordinal() >= earliest
    print("✅ test_gfw_date_clamp passed")


def test_gfw_query_url_encodes_colons():
    """Verify the URL has %3A for colons and %2C for commas in date-range."""
    captured = {}
    def fake_make(url, tok, method="GET", body=None, timeout=60):
        captured["url"] = url
        return {"total": 0.0, "entries": []}
    gfw._make_request = fake_make
    gfw.get_fishing_effort(19.0, 72.8, "2026-05-01", "2026-05-30", token="dummy")
    url = captured["url"]
    assert "date-range=" in url
    assert "%3A" in url, f"Expected %3A (encoded :) in URL, got: {url}"
    assert "%2C" in url, f"Expected %2C (encoded ,) in URL, got: {url}"
    assert "datasets%5B0%5D=" in url or "datasets[0]=" in url
    print(f"✅ test_gfw_query_url_encodes_colons passed")
    print(f"   URL: {url[:130]}...")


if __name__ == "__main__":
    test_gfw_parse_total_field()
    test_gfw_parse_grouped_by_dataset()
    test_gfw_no_token()
    test_gfw_vessels_in_region_by_flag()
    test_gfw_vessels_in_region_grouped()
    test_gfw_date_clamp()
    test_gfw_query_url_encodes_colons()
    print("\n🎉 All 7 GFW tests passed!")
