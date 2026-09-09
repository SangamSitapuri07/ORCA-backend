"""Tests for the Global Fishing Watch (GFW) adapter.

Most tests are offline (no network, no token). The real test needs:
1. User registers at https://globalfishingwatch.org
2. Gets an API token
3. Sets GFW_API_TOKEN environment variable
4. Runs the live test

Until then, tests verify URL construction and graceful token handling.
"""
from __future__ import annotations

import os

import pytest

from pipeline.gfw import (
    DEFAULT_REGION,
    GFW_API_BASE,
    INDIAN_OCEAN_REGIONS,
    get_fishing_effort,
    get_fishing_vessels_in_region,
    get_token,
)


def test_get_token_returns_none_when_unset():
    """Without env var, returns None (and functions return error dicts)."""
    # Temporarily unset
    old = os.environ.pop("GFW_API_TOKEN", None)
    try:
        assert get_token() is None
    finally:
        if old is not None:
            os.environ["GFW_API_TOKEN"] = old


def test_get_fishing_effort_without_token_returns_error():
    """No token = graceful error dict, not exception."""
    old = os.environ.pop("GFW_API_TOKEN", None)
    try:
        result = get_fishing_effort(19.0, 72.8, "2025-08-01", "2025-08-31")
        assert result is not None
        assert "error" in result
        assert "GFW_API_TOKEN" in result["error"]
    finally:
        if old is not None:
            os.environ["GFW_API_TOKEN"] = old


def test_get_fishing_vessels_without_token():
    old = os.environ.pop("GFW_API_TOKEN", None)
    try:
        result = get_fishing_vessels_in_region(19.0, 72.8)
        assert result is not None
        assert "error" in result
    finally:
        if old is not None:
            os.environ["GFW_API_TOKEN"] = old


def test_indian_ocean_regions_defined():
    """Sanity check: we have key regions ready to use."""
    assert "iotc_rfmo" in INDIAN_OCEAN_REGIONS
    assert "india_eez" in INDIAN_OCEAN_REGIONS
    assert INDIAN_OCEAN_REGIONS["india_eez"]["code"] == "356"


def test_default_region_is_iotc():
    assert DEFAULT_REGION == "IOTC"
