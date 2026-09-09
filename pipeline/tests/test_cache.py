"""Tests for the freshness-aware cache.

Run with:    python -m pytest pipeline/tests/test_cache.py -v
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pipeline.cache import Cache, freshness_label


@pytest.fixture
def tmp_cache(monkeypatch, tmp_path):
    """Create a fresh cache in a temp dir for each test."""
    cache = Cache(root=tmp_path / "cache")
    return cache


def test_miss_then_hit(tmp_cache):
    assert not tmp_cache.has_fresh("k1")
    tmp_cache.put("k1", source="test", fresh_for=timedelta(hours=1))
    assert tmp_cache.has_fresh("k1")


def test_expiry(tmp_cache):
    tmp_cache.put("k1", source="test", fresh_for=timedelta(seconds=0))
    # Even with 0 TTL, the entry exists but is immediately stale.
    entry = tmp_cache.get("k1")
    assert entry is not None
    assert not tmp_cache.has_fresh("k1")


def test_put_with_inline_value(tmp_cache):
    tmp_cache.put(
        "k2",
        source="open-meteo",
        fresh_for=timedelta(hours=1),
        inline_value={"wind_kph": 18.5, "wave_m": 1.2},
    )
    e = tmp_cache.get("k2")
    assert e is not None
    assert e.inline_value == {"wind_kph": 18.5, "wave_m": 1.2}
    assert e.source == "open-meteo"


def test_put_with_blob_path(tmp_cache):
    blob = tmp_cache.blobs_dir / "fake.nc"
    blob.write_text("not a real netcdf, just for the test")
    tmp_cache.put(
        "k3",
        source="mosdac",
        fresh_for=timedelta(days=2),
        blob_path=blob,
        metadata={"datasetId": "E06OCM_L4_AC", "date": "2026-08-30"},
    )
    e = tmp_cache.get("k3")
    assert e is not None
    assert e.blob_path == blob
    assert e.metadata["datasetId"] == "E06OCM_L4_AC"


def test_invalidate(tmp_cache):
    tmp_cache.put("k4", source="x", fresh_for=timedelta(hours=1))
    assert tmp_cache.has_fresh("k4")
    tmp_cache.invalidate("k4")
    assert not tmp_cache.has_fresh("k4")
    assert tmp_cache.get("k4") is None


def test_overwrite(tmp_cache):
    tmp_cache.put("k5", source="x", fresh_for=timedelta(hours=1),
                  inline_value="old")
    tmp_cache.put("k5", source="y", fresh_for=timedelta(hours=2),
                  inline_value="new")
    e = tmp_cache.get("k5")
    assert e.source == "y"
    assert e.inline_value == "new"


def test_list_filter_fresh(tmp_cache):
    tmp_cache.put("fresh1", source="x", fresh_for=timedelta(hours=1))
    tmp_cache.put("stale1", source="x", fresh_for=timedelta(seconds=-1))
    all_entries = tmp_cache.list(only_fresh=False)
    fresh_only = tmp_cache.list(only_fresh=True)
    assert {e.key for e in all_entries} == {"fresh1", "stale1"}
    assert {e.key for e in fresh_only} == {"fresh1"}


def test_stats(tmp_cache):
    s = tmp_cache.stats()
    assert "total_entries" in s
    assert "fresh_entries" in s
    assert "cache_root" in s
    assert s["total_entries"] == 0
    tmp_cache.put("k", source="x", fresh_for=timedelta(hours=1))
    s = tmp_cache.stats()
    assert s["total_entries"] == 1
    assert s["fresh_entries"] == 1


def test_freshness_label_recent():
    now = datetime.now(timezone.utc)
    e_fresh = type("E", (), {
        "fetched_at": now - timedelta(seconds=30),
    })()
    assert "now" in freshness_label(e_fresh)

    e_hours = type("E", (), {
        "fetched_at": now - timedelta(hours=3),
    })()
    assert "3h ago" == freshness_label(e_hours)

    e_days = type("E", (), {
        "fetched_at": now - timedelta(days=2, hours=5),
    })()
    assert "2d ago" == freshness_label(e_days)
