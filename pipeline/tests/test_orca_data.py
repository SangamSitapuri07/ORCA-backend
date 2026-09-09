"""Tests for the unified orca_data layer (mostly offline with mocked sources)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline import orca_data


def _mock_all(**overrides):
    """Replace every source with a stub. Pass overrides to customize."""
    # Patch the lazy getters on orca_data directly — they re-import each
    # call, so patching the source modules won't survive a re-import.
    orca_data._get_noaa = lambda: overrides.get(
        "noaa", lambda *a, **kw: {"error": "mock", "source": "NOAA"}
    )
    orca_data._get_incois = lambda: overrides.get(
        "incois", lambda *a, **kw: {"error": "mock", "source": "INCOIS"}
    )
    orca_data._get_occci = lambda: overrides.get(
        "occci", lambda *a, **kw: {"error": "mock", "source": "OC-CCI"}
    )
    orca_data.get_sst_at_point = overrides.get(
        "sst", lambda *a, **kw: {"error": "mock", "source": "Open-Meteo"}
    )
    orca_data._get_gfw_effort = lambda: overrides.get(
        "gfw_effort", lambda *a, **kw: {"error": "mock", "source": "GFW"}
    )
    orca_data._get_gfw_fleet = lambda: overrides.get(
        "gfw_fleet", lambda *a, **kw: {"error": "mock", "source": "GFW"}
    )
    # Silent warmers (ERA5 baseline + today's weather) — stubbed so the
    # offline suite never touches the real archive/weather endpoints.
    # Their results are NOT snapshot fields, so the used/failed source
    # counts below are unaffected.
    orca_data._get_baseline = lambda: overrides.get(
        "baseline", lambda *a, **kw: {}
    )
    orca_data._get_wx_summary = lambda: overrides.get(
        "wx", lambda *a, **kw: {}
    )


def test_zone_snapshot_offline():
    """All 6 sources fail gracefully, snapshot still returned with errors listed."""
    _mock_all()
    snap = orca_data.zone_snapshot(19.0, 72.8, "2026-08-15", include_gfw=True)
    assert snap["lat"] == 19.0
    assert snap["lon"] == 72.8
    assert snap["date"] == "2026-08-15"
    assert "data_sources_failed" in snap
    # 5 sources: Open-Meteo, NOAA, OC-CCI, INCOIS, GFW-effort, GFW-fleet = 6
    assert len(snap["data_sources_failed"]) == 6
    assert "data_sources_used" in snap
    assert len(snap["data_sources_used"]) == 0
    assert "fetched_at" in snap
    assert snap["pfz_score"] is None
    print("✅ test_zone_snapshot_offline passed")


def test_zone_snapshot_partial():
    """Open-Meteo works, others fail — partial snapshot still valid."""
    _mock_all(
        sst=lambda *a, **kw: {
            "sst_max": 29.6, "sst_min": 28.3, "sst_mean": 29.0,
            "wave_max": 2.86, "wave_mean": 2.1, "n_days": 30,
        },
    )
    snap = orca_data.zone_snapshot(19.0, 72.8, "2026-08-15", include_gfw=True)
    assert snap["sst_max"] == 29.6
    assert snap["sst_mean"] == 29.0
    assert snap["wave_max"] == 2.86
    assert "Open-Meteo Marine (SST + waves)" in snap["data_sources_used"]
    assert len(snap["data_sources_failed"]) == 5
    assert snap["pfz_score"] is not None and snap["pfz_score"] >= 0.5
    print(f"✅ test_zone_snapshot_partial passed (pfz_score={snap['pfz_score']})")


def test_zone_snapshot_full():
    """All 4 sources succeed — full snapshot."""
    _mock_all(
        sst=lambda *a, **kw: {
            "sst_max": 28.5, "sst_min": 28.0, "sst_mean": 28.3, "wave_max": 2.5, "wave_mean": 1.8,
        },
        noaa=lambda *a, **kw: {
            "value": 1.5, "units": "mg m^-3", "source": "NOAA ERDDAP DINEOF",
        },
        incois=lambda *a, **kw: {"error": "skipped, NOAA is primary"},
        gfw_effort=lambda *a, **kw: {"hours": 47.3, "vessel_ids": 12},
        gfw_fleet=lambda *a, **kw: {
            "vessel_count": 5, "by_flag": {"IND": 3, "LKA": 2}, "by_gear": {"trawler": 3, "gillnetter": 2},
        },
    )
    snap = orca_data.zone_snapshot(19.0, 72.8, "2026-08-15", include_gfw=True)
    assert snap["chlorophyll"] == 1.5
    assert snap["chlorophyll_source"].startswith("NOAA")
    assert snap["sst_max"] == 28.5
    assert snap["fishing_hours"] == 47.3
    assert snap["vessel_count"] == 5
    assert snap["fleet_by_flag"]["IND"] == 3
    assert snap["fleet_by_gear"]["trawler"] == 3
    assert snap["pfz_score"] is not None and snap["pfz_score"] >= 0.8
    print(f"✅ test_zone_snapshot_full passed (pfz_score={snap['pfz_score']})")


def test_zone_snapshot_incois_fallback():
    """NOAA fails, INCOIS succeeds — fallback path works."""
    _mock_all(
        noaa=lambda *a, **kw: {"error": "mock"},
        incois=lambda *a, **kw: {
            "value": 0.8, "units": "mg m^-3", "source": "INCOIS LAS",
        },
    )
    snap = orca_data.zone_snapshot(19.0, 72.8, "2026-08-15", include_gfw=False)
    assert snap["chlorophyll"] == 0.8
    assert snap["chlorophyll_source"].startswith("INCOIS")
    assert "INCOIS LAS (backup chlorophyll)" in snap["data_sources_used"]
    print("✅ test_zone_snapshot_incois_fallback passed")


def test_grid_snapshot_offline():
    """Grid call with all sources failing — still returns structure."""
    _mock_all()
    g = orca_data.grid_snapshot(18.0, 19.0, 72.0, 73.0, step_deg=1.0, include_gfw=False)
    assert g["n_points"] == 4
    assert len(g["points"]) == 4
    assert all("data_sources_failed" in p for p in g["points"])
    print(f"✅ test_grid_snapshot_offline passed (n_points={g['n_points']})")


def test_pfz_score_optimal_zone():
    """PFZ score peaks at chlorophyll ~1 mg/m^3 and SST 24-29°C."""
    snap = {"chlorophyll": 1.0, "sst_mean": 27.0, "fishing_hours": 5.0}
    score = orca_data._pfz_score(snap)
    assert score is not None and score >= 0.9
    print(f"✅ test_pfz_score_optimal_zone passed (score={score})")


def test_pfz_score_no_data():
    snap = {}
    assert orca_data._pfz_score(snap) is None
    print("✅ test_pfz_score_no_data passed")


def test_safe_helper():
    """The _safe wrapper never raises, returns (result, error_msg)."""
    def boom():
        raise RuntimeError("kaboom")
    res, err = orca_data._safe(boom, label="X")
    assert res is None
    assert "kaboom" in err
    assert "X" in err
    print("✅ test_safe_helper passed")


if __name__ == "__main__":
    test_zone_snapshot_offline()
    test_zone_snapshot_partial()
    test_zone_snapshot_full()
    test_zone_snapshot_incois_fallback()
    test_grid_snapshot_offline()
    test_pfz_score_optimal_zone()
    test_pfz_score_no_data()
    test_safe_helper()
    print("\n🎉 All 8 orca_data tests passed!")


def test_noaa_lag_analysis_from_parallel_job():
    """Today's VIIRS product empty → the upfront PARALLEL 3-day-lag job
    fills chlorophyll with zero extra wall-clock (no serial second fetch —
    that serial tail helped push cold clicks past the /reason deadline)."""
    calls: list[str] = []

    def fake_noaa(lat, lon, d):
        calls.append(d)
        if d == "2026-08-15":
            return {"error": "no product yet"}
        return {"value": 0.7, "units": "mg m^-3", "source": "NOAA ERDDAP DINEOF"}

    _mock_all(noaa=fake_noaa)
    snap = orca_data.zone_snapshot(19.0, 72.8, "2026-08-15", include_gfw=False)
    assert sorted(calls) == ["2026-08-12", "2026-08-15"], calls
    assert snap["chlorophyll"] == 0.7
    assert snap["chlorophyll_source"].startswith("NOAA")
    assert snap["chlorophyll_date"] == "2026-08-12"
    assert "satellite lag" in snap["chlorophyll_note"]
    print("✅ 3-day-lag chlorophyll arrives via the parallel job")


def test_warmers_fill_the_agent_cache_keys():
    """The warm jobs must write the EXACT ttlcache keys the anomaly and
    weather agents read — otherwise reason() pays serial network after
    the gather (the 2026-09-07 /reason 504 root cause)."""
    from pipeline import ttlcache
    from pipeline.agents import anomaly as anomaly_mod
    from pipeline.agents import weather as weather_mod

    ttlcache.clear()
    got = {"archive": 0}
    orig_anom_fetch = anomaly_mod._fetch_baseline
    orig_wx_fetch = weather_mod._fetch
    try:
        _mock_all()
        # The snapshot must call the agents' REAL cached wrappers (they
        # own the cache keys); only the network layer is stubbed.
        orca_data._get_baseline = lambda: anomaly_mod.baseline_cached
        orca_data._get_wx_summary = lambda: weather_mod.get_daily_summary
        anomaly_mod._fetch_baseline = lambda *a, **kw: (
            got.__setitem__("archive", got["archive"] + 1),
            {"baseline_sst_mean": 28.1, "baseline_sst_n": 3, "baseline_wave_mean": 1.2},
        )[1]
        weather_mod._fetch = lambda *a, **kw: {
            "daily": {"wind_speed_10m_max": [5.0]}, "timezone": "mock",
        }

        orca_data.zone_snapshot(19.0, 72.8, "2026-08-15", include_gfw=False)
        stats = ttlcache.cache_stats()
        assert "anom:19.00,72.80:2026-08-15" in stats, f"baseline not warmed: {sorted(stats)}"
        assert "wx:19.00,72.80:2026-08-15" in stats, f"weather not warmed: {sorted(stats)}"

        # The agent's own call afterwards must be a cache HIT — no second
        # archive walk inside the serial 10-agent run.
        r = anomaly_mod.analyze({"lat": 19.0, "lon": 72.8, "date": "2026-08-15", "sst_mean": 29.4})
        assert got["archive"] == 1, f"archive walked {got['archive']} times (must be 1)"
        assert any(f["type"] == "sst_anomaly" for f in r["findings"]), r["findings"]
    finally:
        anomaly_mod._fetch_baseline = orig_anom_fetch
        weather_mod._fetch = orig_wx_fetch
        ttlcache.clear()
    print("✅ warmers fill the exact agent cache keys (reason() pays no serial fetch)")


def test_grid_cells_skip_warmers():
    """Grid sweeps (25+ cells) must NOT multiply archive/ERDDAP load —
    warm_extras=False keeps the old polite conditional fallback."""
    hits = {"climo": 0, "wx": 0, "noaa_calls": []}

    def fake_noaa(lat, lon, d):
        hits["noaa_calls"].append(d)
        return {"value": 1.0, "units": "mg m^-3", "source": "NOAA ERDDAP DINEOF"}

    _mock_all(
        noaa=fake_noaa,
        baseline=lambda *a, **kw: hits.__setitem__("climo", hits["climo"] + 1) or {},
        wx=lambda *a, **kw: hits.__setitem__("wx", hits["wx"] + 1) or {},
    )
    snap = orca_data.zone_snapshot(19.0, 72.8, "2026-08-15", include_gfw=False, warm_extras=False)
    assert hits["climo"] == 0 and hits["wx"] == 0
    assert hits["noaa_calls"] == ["2026-08-15"]  # no upfront lag job for grid cells
    assert snap["chlorophyll"] == 1.0
    print("✅ grid cells keep the polite conditional fallback")
