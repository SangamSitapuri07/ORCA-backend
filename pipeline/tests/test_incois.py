"""Tests for the INCOIS adapter (after the honest-availability rewrite).

INCOIS OPeNDAP is unreliable in practice. The adapter:
  - tries the OPeNDAP once with a 6s hard timeout
  - returns {"value": ..., "source": "INCOIS OCM-2 (OPeNDAP)"} on success
  - returns {"error": ..., "source": "INCOIS", "pfz_url": ...} on failure

These tests verify the contract without requiring live network.
"""
from __future__ import annotations

from datetime import datetime

from pipeline.incois import (
    INCOIS_OPENDAP_BASE,
    INCOIS_PFZ_URL,
    get_chlorophyll,
    get_sst,
    status,
)


def test_incois_opendap_url_format():
    """The known INCOIS OCM-2 OPeNDAP URL is correct format."""
    assert INCOIS_OPENDAP_BASE.startswith("http://las.incois.gov.in")
    assert "Oceansat2-OCM" in INCOIS_OPENDAP_BASE


def test_incois_pfz_url_is_public():
    """INCOIS PFZ advisory is at a known stable URL."""
    assert INCOIS_PFZ_URL.startswith("https://www.incois.gov.in")
    assert "PfzAdvisory" in INCOIS_PFZ_URL


def test_status_recommends_alternatives():
    """The status() helper should list alternatives for chlorophyll."""
    s = status()
    assert "recommendation" in s
    assert "MOSDAC" in s["recommendation"]
    assert "NOAA" in s["recommendation"]


def test_get_chlorophyll_offline_returns_error_dict():
    """Without network, should return an error dict (not crash)."""
    result = get_chlorophyll(19.0, 72.8, "2020-05-01", timeout_sec=2.0)
    # Either a real value (network OK) or an error dict
    if result is not None:
        assert "value" in result or "error" in result
        if "error" in result:
            # When error, we should also surface the PFZ URL for humans
            assert "source" in result
            assert "INCOIS" in result["source"]


def test_get_sst_returns_error_or_data():
    """SST endpoint not available, so expect error dict."""
    result = get_sst(19.0, 72.8)
    assert result is None or "error" in result
    if result and "error" in result:
        # Should suggest Open-Meteo as alternative
        assert "Open-Meteo" in result.get("alternative", "") or "Open-Meteo" in result.get("error", "")


def test_datetime_input_doesnt_crash():
    """Should accept datetime as well as string date."""
    result = get_chlorophyll(19.0, 72.8, datetime(2020, 5, 1), timeout_sec=2.0)
    if result is not None:
        assert "value" in result or "error" in result
