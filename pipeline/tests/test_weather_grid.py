"""Animated weather grid — offline tests (no network; fetchers injected).

Pins the wire contract of GET /api/v1/weather/grid (the feed for the
zoom.earth-style live map at /map): ONE Open-Meteo call with
models=icon_global + wind_speed_unit=ms, speed/direction -> u/v
conversion matching ORCA's compass convention, zip-paired multi-location
responses, frame slicing, honest error dicts, and the integrity of the
bundled REAL demo snapshot (shapes, ranges, and an evening-convection
fingerprint that only real model output would show).
"""
from __future__ import annotations

import math
from pathlib import Path

from pipeline import weather_grid as wg
from pipeline.weather_demo_snapshot import (
    _CL, _D, _G, _PR, _RH, _S, _T, TIMES, demo_payload,
)


def _fake_rows(pairs, frames, rh=60.0):
    rows = []
    for i, (la, lo) in enumerate(pairs):
        rows.append({
            "latitude": la, "longitude": lo,
            "hourly": {
                "time": [f"2026-09-13T{7 + h:02d}:00" for h in range(frames)],
                "wind_speed_10m": [4.0 + (h % 3) for h in range(frames)],
                "wind_direction_10m": [270 for _ in range(frames)],
                "relative_humidity_2m": [rh + i % 5 for _ in range(frames)],
                "temperature_2m": [29.0 + 0.1 * h for h in range(frames)],
            },
        })
    return rows


def test_geometry_and_frames():
    d = wg.get_weather_grid(22.2, 69.4, 3.0, frames=8, grid_n=9,
                            _fetcher=_fake_rows)
    assert d.get("error") is None
    assert len(d["times"]) == 8
    assert len(d["u"]) == len(d["v"]) == len(d["rh"]) == len(d["temp"]) == 8
    assert len(d["u"][0]) == 81
    assert d["lats"][0] == 23.7 and d["lats"][-1] == 20.7      # descending
    assert d["lons"][0] == 67.9 and d["lons"][-1] == 70.9      # ascending
    assert d["step_deg"] == 0.375
    assert d["demo"] is False
    assert d["legend"][0]["value"] == 0 and d["legend"][-1]["value"] == 100


def test_uv_from_speed_and_direction():
    # wind FROM 270 (west) blows TOWARD east: u>0, v~0 — ORCA convention
    d = wg.get_weather_grid(22.2, 69.4, 1.0, frames=2, grid_n=3,
                            _fetcher=_fake_rows)
    assert d["u"][0][0] == 4.0 and d["v"][0][0] == 0.0
    # round-trip: derived u/v must reproduce the reported FROM-direction
    la, lo = d["lats"][1], d["lons"][1]
    idx = 1 * 3 + 1
    u, v = d["u"][0][idx], d["v"][0][idx]
    back = (270 - math.degrees(math.atan2(v, u))) % 360
    assert abs(back - 270) < 0.01


def test_missing_values_become_null_not_fabricated():
    def _holes(pairs, frames):
        rows = _fake_rows(pairs, frames)
        for r in rows[:5]:
            r["hourly"]["wind_direction_10m"] = [None] * frames
        return rows
    d = wg.get_weather_grid(22.2, 69.4, 1.0, frames=2, grid_n=3, _fetcher=_holes)
    assert d.get("error") is None
    assert d["u"][0][0] is None and d["v"][0][0] is None   # first 5 rows holed
    assert d["u"][0][5] is not None                        # rest intact


def test_wire_request_contract(monkeypatch):
    """One call, icon_global, ms winds, zip-paired lists, all 4 variables."""
    seen = {}

    def _fake_http(url, params, timeout=25.0):
        seen.update(params)
        n = params["latitude"].count(",") + 1
        return _fake_rows([(22.0, 69.0)] * n, int(params["forecast_hours"]))

    monkeypatch.setattr(wg, "_http_json", _fake_http)
    d = wg.get_weather_grid(22.2, 69.4, 3.0, frames=8, grid_n=9)
    assert d.get("error") is None
    assert seen["models"] == "icon_global"          # bare "icon" is REJECTED live
    assert seen["wind_speed_unit"] == "ms"
    assert seen["forecast_hours"] == "8"
    assert seen["timezone"] == "UTC"
    for v in ("wind_speed_10m", "wind_direction_10m",
              "relative_humidity_2m", "temperature_2m"):
        assert v in seen["hourly"]
    assert seen["latitude"].count(",") == 80         # 81 points, ONE call
    assert seen["longitude"].count(",") == 80


def test_single_dict_response_is_normalised(monkeypatch):
    # single-coordinate responses can come back as one plain dict —
    # _fetch_grid must wrap it in a list, not crash
    monkeypatch.setattr(wg, "_http_json",
                        lambda url, params, timeout=25.0: {"hourly": {}})
    rows = wg._fetch_grid([(22.0, 69.0), (22.0, 69.5)], 2)
    assert isinstance(rows, list) and len(rows) == 1


def test_honest_error_paths():
    def _boom(pairs, frames):
        raise TimeoutError("simulated outage")
    d = wg.get_weather_grid(22.2, 69.4, _fetcher=_boom)
    assert d.get("error") and "TimeoutError" in d["error"]
    assert "u" not in d                              # nothing invented
    d2 = wg.get_weather_grid(22.2, 69.4, span=2.0, frames=4,      # distinct cache key
                             _fetcher=lambda p, f: _fake_rows(p, f)[:-3])
    assert d2.get("error") and "grid points" in d2["error"]


def test_params_are_clamped():
    d = wg.get_weather_grid(22.2, 69.4, span=99.0, frames=999, grid_n=99,
                            _fetcher=_fake_rows)
    assert d.get("error") is None
    assert d["span_deg"] == wg.SPAN_MAX_DEG
    assert len(d["times"]) == wg.FRAMES_MAX
    assert d["grid_n"] == wg.GRID_N_MAX


# ── bundled demo snapshot (REAL ICON output — integrity, not mocks) ──

def test_demo_snapshot_shapes_and_ranges():
    assert len(_S) == len(_D) == len(_RH) == len(_T) == 117
    assert len(_PR) == len(_G) == len(_CL) == 117
    assert all(len(a) == 8 for a in _S + _D + _RH + _T + _PR + _G + _CL)
    assert TIMES[0] == "2026-09-13T18:00" and TIMES[-1] == "2026-09-14T01:00"
    assert all(0 <= x <= 40 for a in _S for x in a)
    assert all(0 <= x <= 360 for a in _D for x in a)
    assert all(10 <= x <= 100 for a in _RH for x in a)
    assert all(20 <= x <= 40 for a in _T for x in a)
    # relayed verbatim 2026-09-13 19:15 UTC: evening convective rain
    # (two Gulf of Khambhat cells), gusts > speeds, near-total cloud
    # cover over the eastern half; RH dips to 45 over land while the
    # Arabian Sea stays 80+
    assert all(0 <= x <= 20 for a in _PR for x in a)
    assert all(2 <= x <= 45 for a in _G for x in a)
    assert all(0 <= x <= 100 for a in _CL for x in a)
    assert any(x >= 5.0 for a in _PR for x in a)          # real convective cell
    assert max(x for a in _G for x in a) > max(x for a in _S for x in a)


def test_demo_payload_contract():
    d = demo_payload()
    assert d["demo"] is True and d["fetched_at"].startswith("2026-09-13")
    assert len(d["times"]) == 8 and len(d["u"]) == 8 and len(d["u"][0]) == 117
    assert len(d["lats"]) == 9 and len(d["lons"]) == 13   # row/col vectors, not per-point
    assert d["lats"][0] == 26.2 and d["lons"][0] == 62.2 and d["lons"][12] == 76.6
    assert d["grid_rows"] == 9 and d["grid_cols"] == 13
    assert d["step_lat"] == 1.0 and d["step_lon"] == 1.2
    # u/v round-trip: speed & FROM-direction recover exactly
    spd = math.hypot(d["u"][0][0], d["v"][0][0]) * 3.6
    dr = (270 - math.degrees(math.atan2(d["v"][0][0], d["u"][0][0]))) % 360
    assert abs(spd - _S[0][0]) < 0.05 and abs(dr - _D[0][0]) < 1.0
    # new picker fields, transposed [frame][point] like u/v/rh/temp
    for k, raw in (("pr", _PR), ("gust", _G), ("cloud", _CL)):
        assert len(d[k]) == 8 and len(d[k][0]) == 117
        assert d[k][3][40] == raw[40][3]
    assert d["pr"][6][74] == 19.4 and d["gust"][0][0] == 14 and d["cloud"][7][8] == 100


def test_demo_snapshot_convection_signature():
    """Fingerprint of the REAL 18:00->01:00 UTC 2026-09-13 relay: rain
    already active at frame 0 (8.2 mm/h over the Saurashtra coast), the
    evening peak 19.4 mm/h at 21.2N 72.9E (Gulf of Khambhat) at 00:00
    UTC, and the peak cell east of 72E — fabricated or shuffled data
    would not reproduce this."""
    frame_peak = [max(_PR[p][h] for p in range(117)) for h in range(8)]
    assert frame_peak[0] >= 1.5                     # 18:00: active coast cell
    assert max(frame_peak[5:]) >= 6.0               # 23:00-01:00 convective max
    peak = max((x, p, h) for p in range(117) for h in range(8) for x in [_PR[p][h]])
    assert peak[0] == 19.4 and peak[2] == 6 and peak[1] % 13 >= 9  # 21.2N 72.9E, 00:00
    # wind and rain tell the same story: the rainy east is calm, the dry
    # west is windy (monsoon westerlies) — a coherent field, not noise
    west_speed = sum(_S[p][6] for p in range(117) if p % 13 <= 5) / 54
    east_speed = sum(_S[p][6] for p in range(117) if p % 13 >= 9) / 36
    assert west_speed > east_speed


def test_endpoint_demo_and_page():
    from fastapi.testclient import TestClient
    import backend.main as m
    with TestClient(m.app) as c:
        r = c.get("/api/v1/weather/grid?demo=1")
        assert r.status_code == 200
        j = r.json()
        assert j["demo"] is True and len(j["times"]) == 8 and len(j["u"][0]) == 117
        assert c.get("/api/v1/weather/grid").status_code == 422  # coords required
        p = c.get("/map")
        assert p.status_code == 200 and "ORCA Live Weather Map" in p.text
        for k in ("pr", "gust", "cloud"):
            assert len(j[k]) == 8 and len(j[k][0]) == 117, k
        assert "layers" in p.text and 'data-lyr="rain"' in p.text
        assert 'data-lyr="gust"' in p.text and 'data-lyr="cur"' in p.text
        assert "hGust" in p.text and "hRain" in p.text
        assert "tgHum" not in p.text and "tgSst" not in p.text   # moved to rail
        js = c.get("/frontend/weather_map.js")
        assert js.status_code == 200 and "weather/grid" in js.text
        for probe in ("selectLayer", "buildTinies", "palColor", "LAYERS", "pinLL"):
            assert probe in js.text, probe
        # particle bounds guards must use the correct y orientation
        # (by0 = north edge = smaller world-y than by1 = south edge);
        # the inverted form made every particle respawn every tick and
        # the particle animation silently never drew anything
        assert "p.wy < by0 || p.wy > by1" in js.text
        assert "p.wy < by1 || p.wy > by0" not in js.text
        # the demo badge must derive its timestamp from the payload, not
        # hardcode a window (a stale "07Z" badge made fresh data look old)
        assert "07Z" not in js.text and "when(DATA.fetched_at)" in js.text
        # returning tabs must always revalidate the JS (no stale particle
        # bug surviving a browser heuristic cache)
        assert js.headers.get("cache-control") == "no-cache"
        # coverage UX: dashed data box, jump-back button, out-of-view nudge
        assert "fitbox" in c.get("/map").text
        for probe in ("dataBounds", "coverBox", "dashArray"):
            assert probe in js.text, probe
        # playback robustness: crash-proof render loop, visible script
        # errors, clamped frame indices, and a per-build script URL so a
        # cached HTML can never pair with a mismatched JS (that mix left
        # a dead map that looked like "play does nothing")
        assert "loop._err" in js.text
        assert "window.addEventListener('error'" in js.text
        assert "Math.max(0, Math.min(DATA.times.length - 1, Math.floor(tt)))" in js.text
        assert "weather_map.js?v=" in p.text
        assert "click to pin" in c.get("/map").text
        # leaflet must be vendored first-party: a CDN copy dies with
        # 'L is not defined' on any network without unpkg egress (seen
        # live in the sandbox 2026-09-13 — badge stuck on LOADING…)
        page_html = c.get("/map").text
        assert "/frontend/vendor/leaflet.js?v=" in page_html
        assert "/frontend/vendor/leaflet.css?v=" in page_html
        assert "unpkg.com" not in page_html
        # offline basemap: the tile proxy degrades to a drawn graticule
        # tile instead of a 502 (never a blank/broken-looking map)
        from backend.main import _graticule_tile_png
        blob = _graticule_tile_png(7, 88, 56)
        assert blob.startswith(b"\x89PNG") and len(blob) > 500
        # offline nautical CHART: when no tile server is reachable the map
        # must still show real geography — Natural Earth land polygons,
        # 1:10m Kutch coastline and country borders, served first-party
        # (a bare graticule grid made the data look disconnected "floating
        # anywhere": user-visible regression 2026-09-13)
        geo = (Path(__file__).resolve().parents[2] / "frontend"
               / "vendor" / "chart.geojson").read_text()
        for kind in ('"kind":"land"', '"kind":"coast"', '"kind":"border"'):
            assert kind in geo, kind
        assert '"type":"Polygon"' in geo and len(geo) > 100_000
        assert "mountChart" in js.text and "chart.geojson" in js.text
        assert "X-ORCA-Offline" in js.text
        assert 'data-bm="chart"' in c.get("/map").text
        # GPU wind engine (spec §7/§10/§11): WebGL particle renderer on the
        # real u/v field, served first-party + versioned; CPU fallback kept
        gpu_js = (Path(__file__).resolve().parents[2] / "frontend"
                  / "wind_gpu.js").read_text()
        p_html = c.get("/map").text
        assert 'src="/frontend/wind_gpu.js?v=' in p_html
        assert 'id="particlesGL"' in p_html and 'id="tgGPU"' in p_html
        # documented texture encoding: ±80 m/s over 16 bits (0.0024 m/s
        # quantisation — no silent precision loss)
        assert "* 160.0 - 80.0" in gpu_js or "* 160.0 − 80.0" in gpu_js
        assert "65280.0" in gpu_js and "65535.0" in gpu_js
        # missing cells must never render as calm wind (§26): engine refuses
        assert "return false" in gpu_js and "isFinite" in gpu_js
        # advection parity with the CPU engine + fallback wiring in the page
        page_js = js.text
        assert "u_simRate" in gpu_js and "gpuActive()" in page_js
        assert "drawParticles(dt, t)" in page_js          # CPU path preserved
        assert "glC.width = glC.width" in page_js         # clean handover
        # python mirror of the 16-bit ±80 m/s encoding: roundtrip precision
        for val in (-79.99, -12.345, 0.0, 3.3333, 27.18, 79.99):
            e = round((val + 80) / 160 * 65535)
            dec = ((e >> 8) * 256 + (e & 255)) / 65535 * 160 - 80
            assert abs(dec - val) < 0.0025, val
