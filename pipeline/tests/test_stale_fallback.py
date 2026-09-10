"""Tests for ttlcache.remember_last_good / get_last_good — the
last-known-good fallback added so a flaky live source (NOAA, OC-CCI,
MOSDAC, INCOIS, GFW) degrades to a clearly-marked stale reading
instead of a hard failure card."""
import time

import pytest

from pipeline import ttlcache


@pytest.fixture(autouse=True)
def _clear_cache():
    ttlcache.clear()
    yield
    ttlcache.clear()


def test_no_stale_value_returns_none():
    assert ttlcache.get_last_good("missing-key", 3600) is None


def test_remembers_and_returns_stale_copy():
    ttlcache.remember_last_good("noaa:1.0:2.0", {"value": 0.5, "units": "mg/m^3"})
    got = ttlcache.get_last_good("noaa:1.0:2.0", 3600)
    assert got["value"] == 0.5
    assert got["_stale"] is True
    assert got["_stale_age_sec"] >= 0


def test_does_not_mutate_stored_original():
    original = {"value": 0.5}
    ttlcache.remember_last_good("k", original)
    ttlcache.get_last_good("k", 3600)
    assert "_stale" not in original  # stored copy stays clean


def test_expired_entry_returns_none():
    ttlcache.remember_last_good("k", {"value": 1.0})
    # max_age_sec of 0 means "must have been stored in the future" — any
    # nonzero elapsed time (even microseconds) makes it stale-expired.
    time.sleep(0.01)
    assert ttlcache.get_last_good("k", 0) is None


def test_non_dict_values_pass_through_unmarked():
    ttlcache.remember_last_good("k", 42)
    assert ttlcache.get_last_good("k", 3600) == 42


def test_clear_wipes_stale_store_too():
    ttlcache.remember_last_good("k", {"value": 1.0})
    ttlcache.clear()
    assert ttlcache.get_last_good("k", 3600) is None
