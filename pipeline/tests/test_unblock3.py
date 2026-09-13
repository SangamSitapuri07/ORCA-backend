"""The unblocked three — offline machine tests for the 2026-09-13 fix.

Background: E06SCT_L4_AWW6HOURLY / E06OCM_L3_LAC_CQ / E06SCT_L3_WV12 were
disabled pending "product evidence". Live apios re-verification showed the
first and third IDs were simply WRONG (real: E06SCT_L4_AWV6HOURLY and
E06SCT_L2B_WV12), and the second is alive. These tests prove the PARSING
machinery is ready for the real granules — using synthetic fixtures that
mimic the structures MOSDAC actually serves (learned from the earlier
real orders + the live search results):

  * AH analyzed winds: NetCDF-3 grid with U/V — AND the two red herrings
    from the old verdict (global attr title='OSCAT3_GLO_25km', a SIGMA0
    variable). Presence of sigma-0 fields must NOT disqualify wind
    extraction when U/V exist.
  * WV12 L2B swath: HDF5 with 2D per-pixel packed int16 lat/lon inside a
    'Geolocation' subgroup + wind speed/dir + quality flag — exactly why
    the old xarray-only view reported "no usable latitude/longitude".
  * CQ daily composite: NetCDF-4 grid with YYYYMMDD filename (regression
    for the 7-vs-8-digit date bug).

No network, no creds — fixtures are built in tmp_path.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from pipeline import parser
from pipeline.deepdump import deep_dump, render_markdown
from pipeline.extractors import (
    _decode_swath_array,
    extract_wind,
    extract_wind_swath,
)


# ── fixture builders (synthetic, clearly labelled, never shipped) ─────

def _build_ah_grid(path):
    """E06SCTL4AH-style analyzed-wind NetCDF-3 grid, incl. the red herrings."""
    import netCDF4 as nc

    lats = np.arange(5.0, 30.01, 0.25)          # 101 pts
    lons = np.arange(60.0, 95.01, 0.25)         # 141 pts
    with nc.Dataset(path, "w", format="NETCDF3_CLASSIC") as ds:
        ds.title = "OSCAT3_GLO_25km"            # the red herring from the verdict
        ds.source = "Analyzed Winds are computed using Particle Filter Technique"
        ds.createDimension("lat", len(lats))
        ds.createDimension("lon", len(lons))
        v = ds.createVariable("lat", "f4", ("lat",)); v[:] = lats
        v = ds.createVariable("lon", "f4", ("lon",)); v[:] = lons
        u = ds.createVariable("U", "f4", ("lat", "lon")); u[:] = 5.0
        v = ds.createVariable("V", "f4", ("lat", "lon")); v[:] = 3.0
        sig = ds.createVariable("SIGMA0_VALUES", "f4", ("lat", "lon")); sig[:] = 0.5
        ns = ds.createVariable("NS", "i2", ("lat", "lon")); ns[:] = 4
    return path


def _build_wv12_swath(path):
    """E06SCTL2B…-style L2B HDF5 swath: packed 2D geolocation in a subgroup."""
    import h5py

    rows, cols = 60, 80
    lat2d = np.tile(np.arange(rows, dtype=np.float32).reshape(-1, 1) * 0.1 + 20.0,
                    (1, cols))                  # 20.0 … 25.9
    lon2d = np.tile(np.arange(cols, dtype=np.float32).reshape(1, -1) * 0.1 + 70.0,
                    (rows, 1))                  # 70.0 … 77.9
    speed = np.full((rows, cols), 8.5, dtype=np.float32)
    speed[0:5, 0:5] = -9999.0                   # fill patch (land / bad wvc)
    wdir = np.full((rows, cols), 225.0, dtype=np.float32)  # FROM south-west
    flag = np.zeros((rows, cols), dtype=np.int16); flag[0:5, 0:5] = 2

    with h5py.File(path, "w") as f:
        f.attrs["title"] = "EOS-06 Scatterometer L2B wind vectors in swath grid"
        geo = f.create_group("Geolocation")
        lat_v = geo.create_dataset("LAT", data=np.round((lat2d + 90.0) / 0.01).astype(np.int16))
        lat_v.attrs["scale_factor"] = np.float64(0.01)
        lat_v.attrs["add_offset"] = np.float64(-90.0)
        lat_v.attrs["units"] = "degrees_north"
        lon_v = geo.create_dataset("LON", data=np.round(lon2d / 0.01).astype(np.int16))
        lon_v.attrs["scale_factor"] = np.float64(0.01)
        lon_v.attrs["add_offset"] = np.float64(0.0)
        lon_v.attrs["units"] = "degrees_east"
        spd = f.create_dataset("WIND_SPEED", data=speed)
        spd.attrs["_FillValue"] = np.float32(-9999.0)
        spd.attrs["units"] = "m/s"
        dr = f.create_dataset("WIND_DIR", data=wdir)
        dr.attrs["units"] = "degrees"
        fl = f.create_dataset("QUALITY_FLAG", data=flag)
        fl.attrs["long_name"] = "wind vector cell quality"
    return path


def _build_cq_grid(path):
    """E06OCML3CQ-style daily coastal water-quality NetCDF-4 grid."""
    import netCDF4 as nc

    lats = np.arange(7.0, 24.01, 0.25)
    lons = np.arange(68.0, 94.01, 0.25)
    with nc.Dataset(path, "w", format="NETCDF4") as ds:
        ds.title = "Daily composite of coastal water quality for coastal regions of Indian subcontinent"
        ds.createDimension("lat", len(lats))
        ds.createDimension("lon", len(lons))
        ds.createDimension("time", 1)
        v = ds.createVariable("lat", "f4", ("lat",)); v[:] = lats
        v = ds.createVariable("lon", "f4", ("lon",)); v[:] = lons
        t = ds.createVariable("time", "f8", ("time",))
        t.units = "seconds since 1970-01-01"; t[:] = 1789000000.0
        chl = ds.createVariable("CHL", "f4", ("time", "lat", "lon"),
                                fill_value=-9999.0)
        chl[:] = np.full((1, len(lats), len(lons)), 1.75, dtype=np.float32)
        chl.units = "mg m^-3"
    return path


AH_NAME = "E06SCTL4AH_2026255_0000_25km_v1.0.0.nc"
WV12_NAME = "E06SCTL2B2026255_20046_20047_NS_12km_2026-255T10-54-49_v1.0.5.h5"
CQ_NAME = "E06OCML3CQ_20260912_01km_LAC_v1.0.0.nc"


# ── filename parsing — the two wrong IDs were half the bug ────────────

def test_filename_ah_6hourly_cycle_time():
    meta = parser.parse_filename(AH_NAME)
    assert meta["satellite"] == "E06"
    assert meta["instrument"] == "SCT"
    assert meta["processing_level"] == "L4"
    assert meta["product_name"] == "AH"
    assert meta["date"] == datetime(2026, 9, 12, 0, 0)   # day 255, cycle 00:00
    assert meta["resolution_km"] == 25.0
    assert meta["version"] == "v1.0.0"


def test_filename_ah_later_cycle_folds_hhmm():
    meta = parser.parse_filename("E06SCTL4AH_2026254_0012_25km_v1.0.0.nc")
    assert meta["date"] == datetime(2026, 9, 11, 0, 12)


def test_filename_cq_8_digit_date_regression():
    """The old \\d{6,7} regex read '20260912' as Julian '2026091' → Apr 1."""
    meta = parser.parse_filename(CQ_NAME)
    assert meta["product_name"] == "CQ"
    assert meta["date"] == datetime(2026, 9, 12)
    assert meta["resolution_km"] == 1.0


def test_filename_l2b_swath_head():
    meta = parser.parse_filename(WV12_NAME)
    assert meta["processing_level"] == "L2B"
    assert meta["product_name"] == "WV"
    assert meta["date"] == datetime(2026, 9, 12)
    assert meta["resolution_km"] == 12.0
    assert meta["version"] == "v1.0.5"


def test_filename_old_files_unchanged():
    for name, expected in (
        ("E06SCTL4UI_2026244_25km_v1.0.5.nc", datetime(2026, 9, 1)),
        ("E06SCTL4AW_2026243_25km_v1.0.5.nc", datetime(2026, 8, 31)),
    ):
        assert parser.parse_filename(name)["date"] == expected


# ── AWV6HOURLY: sigma-0 presence must not disqualify real wind fields ─

def test_ah_grid_parses_and_extracts_wind_despite_sigma0():
    tmp = _build_ah_grid(_tmp(AH_NAME))
    pf = parser.parse(tmp)
    assert pf.file_type == "NetCDF3"
    assert "U" in pf.variables and "V" in pf.variables
    assert "SIGMA0_VALUES" in pf.variables
    assert pf.file_attrs.get("title") == "OSCAT3_GLO_25km"
    res = extract_wind(pf, 15.0, 72.0)
    assert res is not None and "error" not in res
    assert res["speed"] == pytest.approx(5.831, abs=0.01)
    # u=5 (east), v=3 (north): math angle atan2(3,5)=30.96° ccw-from-east;
    # compass FROM-direction = 270-30.96 = 239.04° (from SW). The old
    # (atan2+180)%360 formula returned 210.96° — convention mix-up fixed.
    assert res["direction_deg"] == pytest.approx(239.04, abs=0.2)


# ── WV12 L2B: 2D packed geolocation in a subgroup ─────────────────────

def test_wv12_swath_detected_with_group_variables():
    tmp = _build_wv12_swath(_tmp(WV12_NAME))
    pf = parser.parse(tmp)
    assert pf.swath is True
    assert pf.swath_lat == "Geolocation/LAT"
    assert pf.swath_lon == "Geolocation/LON"
    # the group walk must see everything, even when xarray shows nothing
    for name in ("Geolocation/LAT", "Geolocation/LON", "WIND_SPEED",
                 "WIND_DIR", "QUALITY_FLAG"):
        assert name in pf.variables, f"missing {name} — group walk failed"


def test_decode_swath_array_applies_packing_and_fill():
    raw = np.array([[10000, 11000]], dtype=np.int16)
    attrs = {"scale_factor": 0.01, "add_offset": -90.0}
    dec = _decode_swath_array(raw, attrs)
    assert dec[0, 0] == pytest.approx(10.0)     # 10000*0.01 - 90
    assert dec[0, 1] == pytest.approx(20.0)
    filled = _decode_swath_array(np.array([[-9999.0]]), {"_FillValue": -9999.0})
    assert np.isnan(filled[0, 0])


def test_wv12_swath_wind_extraction():
    tmp = _build_wv12_swath(_tmp(WV12_NAME))
    pf = parser.parse(tmp)
    res = extract_wind_swath(pf, 20.75, 70.85)
    assert res is not None and "error" not in res
    # file says 8.5 m/s FROM 225° (SW) → u = v = +8.5·sin/cos(45°)
    assert res["speed"] == pytest.approx(8.5, abs=0.02)
    assert res["direction_deg"] == pytest.approx(225.0, abs=0.5)
    assert res["u"] == pytest.approx(6.01, abs=0.05)
    assert res["v"] == pytest.approx(6.01, abs=0.05)
    assert res["flag"] == 0
    assert res["source"] == WV12_NAME


def test_wv12_swath_fill_pixel_is_none_not_fabricated():
    tmp = _build_wv12_swath(_tmp(WV12_NAME))
    pf = parser.parse(tmp)
    # inside the 5×5 fill patch (lat 20.0-20.4, lon 70.0-70.4)
    res = extract_wind_swath(pf, 20.15, 70.15)
    assert res is None


def test_wv12_swath_outside_footprint_is_none():
    tmp = _build_wv12_swath(_tmp(WV12_NAME))
    pf = parser.parse(tmp)
    assert extract_wind_swath(pf, -40.0, 10.0) is None   # Southern Ocean


# ── deep dump: the evidence artifact the block verdict asked for ──────

def test_deepdump_ah_grid_verdict():
    ev = deep_dump(_build_ah_grid(_tmp(AH_NAME)))
    assert ev["checklist"]["verdict"] == "WIND-PARSE-READY"
    assert ev["checklist"]["wind_mode"] == "grid"
    assert ev["checklist"]["wind"]["u_var"] == "U"
    assert ev["global_attrs"]["title"] == "OSCAT3_GLO_25km"
    md = render_markdown(ev)
    assert "WIND-PARSE-READY" in md and "OSCAT3_GLO_25km" in md


def test_deepdump_wv12_swath_verdict():
    ev = deep_dump(_build_wv12_swath(_tmp(WV12_NAME)))
    assert ev["checklist"]["verdict"] == "WIND-PARSE-READY"
    assert ev["checklist"]["wind_mode"] == "swath"
    assert ev["checklist"]["quality_flags"]  # QUALITY_FLAG found
    dec = ev["variables"]["WIND_SPEED"]["decoded"]
    assert dec["valid_pct"] < 100.0           # the fill patch is visible
    assert ev["variables"]["Geolocation/LAT"]["decoded"]["min"] == pytest.approx(20.0, abs=0.01)


def test_deepdump_cq_is_honest_not_wind():
    ev = deep_dump(_build_cq_grid(_tmp(CQ_NAME)))
    assert ev["checklist"]["verdict"] == "NOT-WIND"
    assert ev["checklist"]["latlon"]["present"] is True
    assert ev["filename_parse"]["date"].startswith("2026-09-12")


def test_deepdump_json_serializable():
    import json
    ev = deep_dump(_build_wv12_swath(_tmp(WV12_NAME)))
    json.dumps(ev, default=str)  # must not raise


# ── helper ────────────────────────────────────────────────────────────

def _tmp(name, tmp_dir=None):
    import pathlib, tempfile
    d = pathlib.Path(tempfile.mkdtemp()) if tmp_dir is None else tmp_dir
    return d / name
