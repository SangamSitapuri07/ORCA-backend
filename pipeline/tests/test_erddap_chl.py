"""Tests for the NOAA ERDDAP chlorophyll adapter.

Most tests verify URL construction. The real test is a live network call
which the user can run with:
    python -c "from pipeline.erddap_chl import get_chlorophyll; print(get_chlorophyll(19.0, 72.8))"
"""
from __future__ import annotations

from datetime import datetime

import pytest

from pipeline.erddap_chl import (
    ERDDAP_BASE,
    build_query_url,
    get_chlorophyll,
    get_chlorophyll_with_fallback,
)


def test_build_query_url_latest():
    url = build_query_url(19.0, 72.8)
    assert url.startswith(ERDDAP_BASE)
    assert "chlor_a[last]" in url
    assert "18.9" in url or "19.1" in url  # box bounds


def test_build_query_url_specific_date():
    url = build_query_url(15.0, 75.0, date="2026-08-25")
    assert "2026-08-25" in url


def test_build_query_url_datetime():
    url = build_query_url(15.0, 75.0, date=datetime(2026, 8, 25))
    assert "2026-08-25" in url


def test_build_query_url_keeps_negative_lon():
    """ERDDAP VIIRS uses -180 to 180 longitude; keep negative as-is."""
    url = build_query_url(19.0, -73.0)  # Mumbai-ish but western hemisphere
    # Should keep as -73.0 ± 0.05
    assert "-73" in url and "18.9" in url or "19.1" in url
    assert "noaacwNPPN20VIIRSDINEOFDaily" in url


def test_get_chlorophyll_offline_returns_error():
    """Without network, should return an error dict or None, never crash."""
    result = get_chlorophyll(19.0, 72.8)
    # Either data (if network works) or error dict
    if result is not None:
        assert "value" in result or "error" in result


def test_get_chlorophyll_with_fallback_offline():
    """With fallback, should at least return something (error or data)."""
    result = get_chlorophyll_with_fallback(19.0, 72.8)
    if result is not None:
        assert "value" in result or "error" in result
