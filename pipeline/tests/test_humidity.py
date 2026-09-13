"""Humidity map field — offline tests (no network; fetcher is injected).

The zoom.earth-style RH layer rebuilt from DWD ICON via Open-Meteo.
These tests pin the grid geometry, the zip-pairing of multi-location
responses, forecast-hour selection, palette/legend consistency, land
flagging, and the honest error path. No fabricated weather is used as a
*claim* — synthetic payloads are clearly fixtures standing in for the
wire format documented at open-meteo.com.
"""
from __future__ import annotations

import pytest

from pipeline import humidity


def _fake_rows(pairs, hours_ahead, rh_base=60.0, n_hours=None):
    """Build a realistic Open-Meteo multi-location response list."""
    n_hours = n_hours or (hours_ahead + 1)
    rows = []
    for i, (p_lat, p_lon) in enumerate(pairs):
        rh_series = [round(rh_base + i % 5 + h * 0.5, 2) for h in range(n_hours)]
        rows.append({
            "latitude": p_lat,
            "longitude": p_lon,
            "hourly": {
                "time": [f"2026-09-13T{h:02d}:00" for h in range(n_hours)],
                "relative_humidity_2m": rh_series,
                "temperature_2m": [28.0 + (h * 0.1) for h in range(n_hours)],
                "dew_point_2m": [24.0 for _ in range(n_hours)],
            },
        })
    return rows


@pytest.fixture(autouse=True)
def _no_landmask(monkeypatch):
    """Deterministic land flags — the real GLOBE mask can't download in CI."""
    monkeypatch.setattr("pipeline.landmask.is_land", lambda lat, lon: lat > 23.5)


def test_grid_geometry_cartesian():
    pairs = humidity._grid_pairs(22.2, 69.4, span=4.0, n=5)
    assert len(pairs) == 25                      # 5×5 cartesian, not diagonal
    assert pairs[0] == (24.2, 67.4)              # north-west corner first
    assert pairs[-1] == (20.2, 71.4)             # south-east corner last
    # every row shares a latitude, every column a longitude
    lats = {p[0] for p in pairs}
    lons = {p[1] for p in pairs}
    assert len(lats) == 5 and len(lons) == 5


def test_field_build_maps_values_and_summary():
    res = humidity.get_humidity_field(
        22.2, 69.4, span=4.0, hours_ahead=0,
        _fetcher=lambda pairs, h: _fake_rows(pairs, h, rh_base=70.0),
    )
    assert res.get("error") is None
    assert res["n_points"] == 81                  # default 9×9
    assert res["step_deg"] == pytest.approx(0.5, abs=0.001)
    assert res["valid_time"] == "2026-09-13T00:00"
    p0 = res["points"][0]
    assert p0["rh_pct"] == 70.0
    assert p0["temp_c"] == 28.0
    assert p0["dew_point_c"] == 24.0
    assert p0["dew_depression_c"] == 4.0
    assert p0["color"] == humidity.color_for_rh(70.0)
    assert res["summary"]["rh_min"] is not None
    assert res["summary"]["rh_min"] <= res["summary"]["rh_mean"] <= res["summary"]["rh_max"]


def test_forecast_hour_selection():
    # 5 hours of series, ask for hour 3 → values and valid_time from index 3
    res = humidity.get_humidity_field(
        22.0, 69.0, span=1.0, hours_ahead=3, grid_n=3,
        _fetcher=lambda pairs, h: _fake_rows(pairs, h, n_hours=5),
    )
    assert res["hours_ahead"] == 3
    assert res["valid_time"] == "2026-09-13T03:00"
    # fake rows: rh = 60 + (i % 5) + h*0.5 → hour 3 adds 1.5
    assert res["points"][0]["rh_pct"] == pytest.approx(61.5, abs=0.01)


def test_land_flag_is_carried_not_assumed():
    # centre 23.0 + span 2 → lats {24.0, 23.0, 22.0}: the >23.5N row is
    # land, the rest sea — flags must reflect the mask, not a guess
    res = humidity.get_humidity_field(
        23.0, 69.0, span=2.0, grid_n=3,
        _fetcher=lambda pairs, h: _fake_rows(pairs, h),
    )
    flags = [p["land"] for p in res["points"]]
    assert True in flags and False in flags       # >23.5N marked land (fixture)


def test_palette_and_legend_consistency():
    assert humidity.color_for_rh(0) == humidity.PALETTE[0][1]
    assert humidity.color_for_rh(100) == humidity.PALETTE[-1][1]
    assert humidity.color_for_rh(None) == "#808080"           # unknown → grey
    mid = humidity.color_for_rh(50)                            # between stops
    assert mid.startswith("#") and len(mid) == 7
    leg = humidity.legend()
    assert [s["value"] for s in leg] == [r for r, _ in humidity.PALETTE]
    assert leg[0]["color"] == humidity.PALETTE[0][1]
    assert all("label" in s for s in leg)


def test_honest_error_path_never_fabricates():
    def _boom(pairs, hours):
        raise TimeoutError("simulated ICON outage")
    res = humidity.get_humidity_field(22.2, 69.4, _fetcher=_boom)
    assert res.get("error") and "TimeoutError" in res["error"]
    assert "points" not in res                                    # nothing invented


def test_mismatched_location_count_is_an_error():
    res = humidity.get_humidity_field(
        22.0, 69.0, grid_n=3,
        _fetcher=lambda pairs, h: _fake_rows(pairs[:-2], h),     # server short-changed us
    )
    assert res.get("error") and "grid points" in res["error"]


def test_params_are_clamped():
    res = humidity.get_humidity_field(
        22.0, 69.0, span=500.0, hours_ahead=999, grid_n=99,
        _fetcher=lambda pairs, h: _fake_rows(pairs, h),
    )
    assert res.get("error") is None
    assert res["span_deg"] == humidity.SPAN_MAX_DEG
    assert res["hours_ahead"] == humidity.HOURS_MAX
    assert res["grid_n"] == humidity.GRID_N_MAX


def test_wire_request_uses_icon_global(monkeypatch):
    """The real request must ask for icon_global (bare 'icon' is rejected
    by the API — verified live 2026-09-13) and zip-paired coordinate lists."""
    seen = {}

    def _fake_http(url, params, timeout=20.0):
        seen["url"] = url
        seen["params"] = params
        return [{
            "hourly": {"time": ["2026-09-13T06:00"],
                       "relative_humidity_2m": [60],
                       "temperature_2m": [30.0],
                       "dew_point_2m": [22.0]},
        }] * (params["latitude"].count(",") + 1)  # one row per location

    monkeypatch.setattr(humidity, "_http_json", _fake_http)
    res = humidity.get_humidity_field(22.2, 69.4, span=1.0, grid_n=3, hours_ahead=0)
    assert res.get("error") is None
    assert seen["params"]["models"] == "icon_global"
    assert seen["params"]["forecast_hours"] == "1"
    assert seen["params"]["timezone"] == "UTC"
    assert "relative_humidity_2m" in seen["params"]["hourly"]
    # 3×3 grid → 9 zip-paired coordinates in ONE call
    assert seen["params"]["latitude"].count(",") == 8
    assert seen["params"]["longitude"].count(",") == 8
    assert res["n_points"] == 9
