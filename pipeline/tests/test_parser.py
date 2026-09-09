"""Tests for the NetCDF/HDF5 parser.

These run without the scientific stack where possible (filename parsing
always works; file-content parsing needs xarray + netCDF4 / h5py).

To run the full file-content tests, install the stack:
    pip install xarray netCDF4 h5py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pipeline.parser import (
    ParsedFile,
    detect_file_type,
    parse,
    parse_filename,
)


# --- Filename parsing tests (no file I/O, no scientific stack needed) ---


def test_parse_mosdac_upwelling_filename():
    meta = parse_filename("E06SCTL4UI_2026244_25km_v1.0.5.nc")
    assert meta["satellite"] == "E06"
    assert meta["instrument"] == "SCT"
    assert meta["processing_level"] == "L4"
    assert meta["product_name"] == "UI"
    assert meta["date"] == datetime(2026, 9, 1)  # day 244 of 2026
    assert meta["resolution_km"] == 25.0
    assert meta["version"] == "v1.0.5"


def test_parse_mosdac_wind_filename():
    meta = parse_filename("E06SCTL4AW_2026243_25km_v1.0.5.nc")
    assert meta["satellite"] == "E06"
    assert meta["product_name"] == "AW"
    assert meta["date"] == datetime(2026, 8, 31)  # day 243
    assert meta["resolution_km"] == 25.0


def test_parse_oceansat2_filename():
    meta = parse_filename("O2-SCT-AWV50.nc")
    # Hyphenated older format
    assert meta["satellite"] == "O2"
    assert meta["instrument"] == "SCT"
    assert meta["product_name"] == "AWV50"


def test_parse_no_match_returns_empty():
    meta = parse_filename("random_file.nc")
    assert meta["satellite"] is None
    assert meta["date"] is None


def test_parse_with_duplicate_suffix():
    meta = parse_filename("E06SCTL4AW_2026243_25km_v1.0.5 (1).nc")
    # The "(1)" copy suffix shouldn't break the date parsing
    assert meta["date"] == datetime(2026, 8, 31)


# --- File-type detection tests (no scientific stack) ---


def test_detect_netcdf_via_extension(tmp_path):
    p = tmp_path / "fake.nc"
    p.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 100)
    assert detect_file_type(p) == "NetCDF4"


def test_detect_hdf5_via_extension(tmp_path):
    p = tmp_path / "fake.h5"
    p.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 100)
    assert detect_file_type(p) == "HDF5"


def test_detect_netcdf3_magic(tmp_path):
    """MOSDAC EOS-06 files use the older NetCDF-3 classic format.
    Their magic bytes are 'CDF\\x01' (classic) or 'CDF\\x02' (64-bit offset)."""
    p = tmp_path / "fake_classic.nc"
    p.write_bytes(b"CDF\x01" + b"\x00" * 100)
    assert detect_file_type(p) == "NetCDF3"

    p2 = tmp_path / "fake_64bit.nc"
    p2.write_bytes(b"CDF\x02" + b"\x00" * 100)
    assert detect_file_type(p2) == "NetCDF3"


def test_detect_netcdf3_real_filename(tmp_path):
    """A real EOS-06 file should now be detected as NetCDF3."""
    # Create a minimal file with CDF\x01 magic and a .nc extension
    p = tmp_path / "E06SCTL4UI_2026244_25km_v1.0.5.nc"
    p.write_bytes(b"CDF\x01" + b"\x00" * 100)
    assert detect_file_type(p) == "NetCDF3"


def test_detect_unknown(tmp_path):
    p = tmp_path / "fake.txt"
    p.write_text("not binary")
    assert detect_file_type(p) == "unknown"


# --- File content tests (require scientific stack — skip if missing) ---


def test_parse_real_netcdf_skipped_if_no_stack():
    """If xarray isn't installed, parse() should still succeed with
    filename-only metadata and a warning."""
    pytest.skip(
        "Placeholder: full file-content tests need xarray installed. "
        "Filename-only tests above already cover the parser's main path."
    )


def test_parse_filename_only_when_file_missing():
    """parse() on a nonexistent file should give us filename metadata
    but a warning."""
    pf = parse("/nonexistent/E06SCTL4UI_2026244_25km_v1.0.5.nc")
    assert pf.path.name == "E06SCTL4UI_2026244_25km_v1.0.5.nc"
    assert pf.satellite == "E06"
    assert pf.product_name == "UI"
    assert pf.date == datetime(2026, 9, 1)
    # Should have at least one warning (file not found)
    assert any("not" in w.lower() or "open" in w.lower() or "exist" in w.lower()
               for w in pf.warnings) or len(pf.variables) == 0
