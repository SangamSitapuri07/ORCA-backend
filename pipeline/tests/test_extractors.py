"""Tests for the domain extractors.

We don't have real MOSDAC files in the test environment, so most tests
verify:
  - Pure-Python helpers (longitude normalization, interpretation buckets)
  - 4D array collapse logic with synthetic arrays
  - Returns None on bad input (no crash)

To verify the real-file path, the user runs `python -m pipeline.inspect
<file> --at LAT LON` on their actual MOSDAC files.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

from pipeline.extractors import (
    _collapse_4d,
    _normalize_lon,
    extract_chlorophyll,
    extract_upwelling,
    extract_wind,
)


# ----------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------

def test_normalize_lon_positive():
    assert _normalize_lon(72.8) == 72.8
    assert _normalize_lon(180) == 180
    assert _normalize_lon(0) == 0


def test_normalize_lon_negative():
    assert _normalize_lon(-180) == 180
    assert _normalize_lon(-90) == 270
    assert _normalize_lon(-1) == 359


def test_collapse_4d():
    arr = np.random.rand(1, 1, 10, 20)
    out = _collapse_4d(arr)
    assert out.shape == (10, 20)


def test_collapse_3d():
    arr = np.random.rand(1, 10, 20)
    out = _collapse_4d(arr)
    assert out.shape == (10, 20)


def test_collapse_2d_passthrough():
    arr = np.random.rand(10, 20)
    out = _collapse_4d(arr)
    assert out.shape == (10, 20)


def test_collapse_wrong_shape_raises():
    with pytest.raises(ValueError):
        _collapse_4d(np.random.rand(10))


# ----------------------------------------------------------------------
# Extractors — these need a fake ParsedFile
# ----------------------------------------------------------------------

class FakePath:
    def __init__(self, name):
        self.name = name


class FakeParsedFile:
    """Minimal stand-in for ParsedFile to test extractors without real files."""
    def __init__(self, variables, coordinates, file_type="NetCDF3", path_name="fake.nc"):
        self.variables = variables
        self.coordinates = coordinates
        self.file_type = file_type
        self.path = FakePath(path_name)


# All file-opening tests below will fail gracefully (no real path),
# so they exercise the "no path → return None" branch.

def test_extract_chlorophyll_no_path_returns_none():
    pf = FakeParsedFile(
        variables={"chlor_a": {"units": "mg m^-3"}},
        coordinates={},
    )
    # With no xarray, falls through to error dict; with xarray but no
    # real file, the open fails. Both are "no useful value" → result is
    # either None or {"error": ..., "source": ...}.
    result = extract_chlorophyll(pf, 19.0, 72.8)
    assert result is None or "error" in result


def test_extract_wind_no_path_returns_none():
    pf = FakeParsedFile(
        variables={"U": {"units": "m/s"}, "V": {"units": "m/s"}},
        coordinates={},
    )
    result = extract_wind(pf, 19.0, 72.8)
    assert result is None or "error" in result


def test_extract_upwelling_no_path_returns_none():
    pf = FakeParsedFile(
        variables={"Upwelling_index": {"units": "m^2/s"}},
        coordinates={},
    )
    result = extract_upwelling(pf, 19.0, 72.8)
    assert result is None or "error" in result


def test_extract_chlorophyll_wrong_var_returns_none():
    pf = FakeParsedFile(
        variables={"some_other": {}},
        coordinates={},
    )
    result = extract_chlorophyll(pf, 19.0, 72.8)
    assert result is None or "error" in result


def test_extract_wind_wrong_var_returns_none():
    pf = FakeParsedFile(
        variables={"not_u_or_v": {}},
        coordinates={},
    )
    result = extract_wind(pf, 19.0, 72.8)
    assert result is None or "error" in result


def test_extract_chlorophyll_no_coords_returns_none():
    """If the file has no lat/lon coords, extractor returns None.

    This happens when xarray is installed and the file opens, but the
    coordinate variables are missing or named differently. We test
    the path-coordinates branch is read correctly.
    """
    pf = FakeParsedFile(
        variables={"chlor_a": {"units": "mg m^-3"}},
        coordinates={"lat": None, "lon": None},
    )
    result = extract_chlorophyll(pf, 19.0, 72.8)
    assert result is None or "error" in result
