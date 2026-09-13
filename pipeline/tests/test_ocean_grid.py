"""Ocean grid (currents + waves + SST) — offline tests, no network.

Pins the wire contracts of GET /api/v1/ocean/grid: ONE ERDDAP call per
satellite product (NOAA CoastWatch currents, CoralTemp SST) with the
verified dataset IDs and bracket-encoded constraints, ONE Open-Meteo
Marine call with zip-paired coordinate lists; null-safe bilinear
interpolation onto the weather-grid lattice (coastline = nulls stay
null); per-source honest errors; and the integrity of the bundled REAL
demo snapshot (2026-09-13 relay) incl. spot-checks against the raw API
responses and the genuine Gulf-of-Kutch jet.
"""
from __future__ import annotations

import math

import pytest

from pipeline import ocean_grid as og
from pipeline.ocean_demo_snapshot import (
    CUR_LATS, CUR_LONS, CUR_U, CUR_V, SST, SST_LATS, SST_LONS, WAV_TIMES,
    WH, WP, demo_payload,
)


import re
import urllib.parse


def _box(url):
    """Parse (lats, lons) actually requested from an ERDDAP griddap URL."""
    url = urllib.parse.unquote(url)          # brackets are %5B/%5D-encoded
    pairs = re.findall(r"\[?\(([\d.]+)\):\d+:\(([\d.]+)\)\]", url)
    la0, la1 = float(pairs[0][0]), float(pairs[0][1])   # 1st constraint = lat
    lo0, lo1 = float(pairs[1][0]), float(pairs[1][1])   # 2nd = lon
    lats = [round(la0 + 0.25 * i, 4) for i in range(int((la1 - la0) / 0.25) + 1)]
    lons = [round(lo0 + 0.25 * i, 4) for i in range(int((lo1 - lo0) / 0.25) + 1)]
    return lats, lons


def _fake_fetch(url):
    if "noaacwBLENDEDNRTcurrentsDaily" in url:
        lats, lons = _box(url)
        rows = [["2026-09-10T00:00:00Z", la, lo,
                 0.1 if lo < 69.0 else None, 0.2 if lo < 69.0 else None]
                for la in lats for lo in lons]
        return {"table": {"rows": rows}}
    if "noaacrwsstDaily" in url:
        lats, lons = _box(url)
        rows = [["2026-09-11T12:00:00Z", la, lo, 28.0 + (la - 22.0) * 0.1]
                for la in lats for lo in lons]
        return {"table": {"rows": rows}}
    if "marine-api" in url:
        n = urllib.parse.unquote(url).split("latitude=")[1].split("&")[0].count(",") + 1
        return [{"hourly": {"time": ["2026-09-13T08:00", "2026-09-13T09:00",
                                     "2026-09-13T10:00"],
                            "wave_height": [1.5, 1.6, 1.7],
                            "wave_direction": [220, 221, 222],
                            "wave_period": [11.0, 10.9, 10.8]}} for _ in range(n)]
    raise AssertionError("unexpected url " + url[:70])


def test_wire_urls():
    u = og.currents_url(23.7, 20.7, 67.9, 70.9)
    assert "noaacwBLENDEDNRTcurrentsDaily.json" in u
    assert "u_current" in u and "v_current" in u
    assert "%5B(last)%5D" in u and "(20.7):1:(23.7)" in u and "(67.9):1:(70.9)" in u
    u2 = og.sst_url(23.7, 20.7, 67.9, 70.9)
    assert "noaacrwsstDaily.json" in u2 and "analysed_sst" in u2
    assert ":5:(23.7)" in u2                      # 0.05° native, stride 5 = 0.25°
    u3 = og.waves_url([(22.2, 69.4), (22.2, 69.775)], 8)
    assert "marine-api.open-meteo.com" in u3
    assert "wave_height%2Cwave_direction%2Cwave_period" in u3
    assert "forecast_hours=10" in u3              # frames + 2, then sliced
    assert "latitude=22.2000%2C22.2000" in u3.replace("%2C", "%2C")


def test_geometry_interp_and_null_coast():
    d = og.get_ocean_grid(22.375, 69.0, 1.0, frames=3, grid_n=4, _fetch=_fake_fetch)
    assert d.get("error") is None
    assert len(d["lats"]) == 4 and d["lats"][0] == 22.875      # descending
    assert len(d["cu"]) == 16
    # open-water point: bilinear of valid corners
    sea = [p for p in range(16) if d["cu"][p] is not None]
    assert sea, "expected some sea points"
    assert all(abs(d["cu"][p] - 0.1) < 1e-6 and abs(d["cv"][p] - 0.2) < 1e-6
               for p in sea)
    # deep-land points stay null, never fabricated; near-shore points take
    # the nearest VALID corner (documented coastal rule)
    assert d["cu"][3] is None and d["cu"][15] is None      # 69.5 degE = land
    assert d["cu"][2] == 0.1                               # near-shore -> sea corner
    assert d["sources"]["currents"]["time"] == "2026-09-10T00:00:00Z"
    assert d["sources"]["sst"]["time"] == "2026-09-11T12:00:00Z"
    # waves: 3 frames, 16 points, first frame values
    assert d["times"] == ["2026-09-13T08:00", "2026-09-13T09:00", "2026-09-13T10:00"]
    assert d["wh"][0][0] == 1.5 and d["wd"][2][15] == 222 and d["wp"][1][7] == 10.9
    assert d["wave_legend"][0]["value"] == 0


def test_interp_exact_and_bilinear():
    g = {21.0: {69.0: 1.0, 69.25: 2.0}, 20.75: {69.0: 3.0, 69.25: 4.0}}
    lats, lons = [21.0, 20.75], [69.0, 69.25]
    assert og._interp(g, lats, lons, 21.0, 69.0) == 1.0          # exact corner
    mid = og._interp(g, lats, lons, 20.875, 69.125)
    assert abs(mid - 2.5) < 1e-9                                  # bilinear centre
    assert og._interp(g, lats, lons, 21.5, 69.0) is None          # outside
    g2 = {21.0: {69.0: None, 69.25: 2.0}, 20.75: {69.0: None, 69.25: 4.0}}
    v = og._interp(g2, lats, lons, 21.0, 69.0)                    # coastal null
    assert v in (2.0, 4.0)                                        # nearest valid


def test_per_source_errors_are_independent():
    def boom_cur(url):
        if "noaacwBLENDEDNRTcurrentsDaily" in url:
            raise TimeoutError("satellite outage")
        return _fake_fetch(url)
    d = og.get_ocean_grid(22.375, 69.0, 2.0, frames=2, grid_n=3, _fetch=boom_cur)
    assert d.get("error") is None                      # partial data still served
    assert d["cu"][0] is None and d["cv"][0] is None
    assert "TimeoutError" in d["errors"]["currents"]
    assert any(v is not None for v in d["sst"])        # SST unaffected
    assert d["wh"][0][0] == 1.5                        # waves unaffected

    def boom_all(url):
        raise TimeoutError("total outage")
    d2 = og.get_ocean_grid(22.375, 69.0, 2.5, frames=3, grid_n=4,   # fresh cache key
                           _fetch=boom_all)
    assert d2.get("error") and "TimeoutError" in d2["error"]


def test_params_clamped_and_marine_dict_normalised():
    d = og.get_ocean_grid(22.375, 69.0, 99.0, frames=999, grid_n=99,
                          _fetch=_fake_fetch)
    assert d.get("error") is None
    assert d["span_deg"] == og.SPAN_MAX_DEG and d["grid_n"] == og.GRID_N_MAX


# ── bundled demo snapshot (REAL relayed values — integrity, not mocks) ──

def test_demo_snapshot_shapes():
    assert len(CUR_LATS) == 14 and len(CUR_LONS) == 16
    assert all(len(r) == 16 for r in CUR_U + CUR_V + SST)
    assert len(SST_LATS) == 14 and len(SST_LONS) == 16
    assert WAV_TIMES[0] == "2026-09-13T08:00" and len(WAV_TIMES) == 16
    for table in (CUR_U, CUR_V, SST):
        for r in table:
            assert all(v is None or -1.5 <= v <= 30 for v in r)
    for p, vals in WH.items():
        assert 0 <= p <= 80 and len(vals) == 16
        assert all(0 <= x <= 5 for x in vals)
    for vals in WP.values():
        assert all(0 <= x <= 15 for x in vals)


def test_demo_spot_checks_vs_raw_api():
    """Verbatim values from the relayed ERDDAP / Marine responses."""
    assert CUR_U[11][2] == 0.2031 and CUR_V[11][2] == -0.1386   # 21.125, 68.125
    assert CUR_U[4][10] == 0.7617 and CUR_V[4][9] == 0.7592     # Gulf jet (real!)
    assert SST[7][0] == 27.97                                    # 22.025, 67.525
    assert WH[80][0] == 1.02                                     # 20.7, 70.9 open sea
    assert WP[80][0] == 9.45


def test_demo_payload_contract():
    d = demo_payload(8)
    assert d["demo"] is True and d["errors"] == {}
    assert len(d["times"]) == 8 and d["times"][0] == "2026-09-13T08:00"
    assert len(d["cu"]) == 81 and len(d["wh"]) == 8 and len(d["wh"][0]) == 81
    assert d["lats"][0] == 23.7 and d["lons"][0] == 67.9 and d["step_deg"] == 0.375
    assert d["wh"][0][3] is None                       # land stays null
    # the Gulf-of-Kutch jet must survive interpolation
    sp = [math.hypot(d["cu"][p], d["cv"][p]) for p in range(81)
          if d["cu"][p] is not None]
    assert max(sp) > 0.5
    # currents time is the satellite date, not "now"
    assert d["sources"]["currents"]["time"] == "2026-09-10T00:00:00Z"
    assert d["sources"]["sst"]["time"] == "2026-09-11T12:00:00Z"


def test_endpoint_demo_and_page():
    from fastapi.testclient import TestClient
    import backend.main as m
    with TestClient(m.app) as c:
        r = c.get("/api/v1/ocean/grid?demo=1")
        assert r.status_code == 200
        j = r.json()
        assert j["demo"] and len(j["wh"][0]) == 81
        assert c.get("/api/v1/ocean/grid").status_code == 422
        h = c.get("/map").text
        for probe in ("wavemark", "currents", "tgCur", "tgWaves", "tgSst", "hSea"):
            assert probe in h, probe
        js = c.get("/frontend/weather_map.js").text
        for probe in ("loadOcean", "sampleSea", "drawWaves", "drawCurParticles",
                      "waveFrameAt", "SST_PALETTE"):
            assert probe in js, probe
