"""Regression tests for the 2026-09-04 screenshot-review bug batch.

Bug #3: Satellite tag followed the CROSS-CHECK source's success instead of
        the primary (NOAA) measurement — cloud-masked OC-CCI flipped the
        chip to "no data" while real chlorophyll was displayed.
Bug #2: Marine Risk quoted a 2.5 m+ rough-seas warning yet concluded
        "low" because wave_caution weighed only 1 (threshold is 2).
Bug #1: Gale-force gusts next to a "calm" sustained reading never
        escalated — gust severity was always just "info".
"""
from __future__ import annotations

from pipeline.agents import marine_risk, satellite, weather


# ── Bug #3: satellite tag must follow the PRIMARY measurement ─────────

def test_satellite_low_chl_without_crosscheck_is_low_not_unknown():
    """chl present (NOAA) but OC-CCI cloud-masked → 'low', NOT 'unknown'."""
    snap = {
        "chlorophyll": 0.21,
        "chlorophyll_source": "NOAA ERDDAP",
        "chlorophyll_unit": "mg/m^3",
        # note: no chlorophyll_occci key → cross-check absent
    }
    res = satellite.analyze(snap)
    assert res["risk_level"] == "low", res
    # And the honesty note about the missing cross-check must be visible
    types = [f["type"] for f in res["findings"]]
    assert "chl_cross_check_missing" in types


def test_satellite_absent_chl_still_unknown():
    """Genuinely no chlorophyll at all → 'unknown' (that IS no data)."""
    res = satellite.analyze({"chlorophyll": None})
    assert res["risk_level"] == "unknown"


def test_satellite_bloom_still_moderate():
    snap = {"chlorophyll": 6.5, "chlorophyll_source": "NOAA", "chlorophyll_unit": "mg/m^3"}
    assert satellite.analyze(snap)["risk_level"] == "moderate"


# ── Review round-5: large MOSDAC gaps must not hide behind the bloom story ──

def test_satellite_mosdac_large_gap_flags_outlier_not_blanket_bloom():
    """8.5x gap with NOAA+OC-CCI agreeing → OCM-3 named the outlier, value
    NOT counted as confirmation, pixel forensics point at the lone hot
    pixel. Blanket 'treat the fine structure as real' text is gone."""
    snap = {
        "chlorophyll": 0.35, "chlorophyll_source": "NOAA", "chlorophyll_unit": "mg/m^3",
        "chlorophyll_date": "2026-09-01",
        "chlorophyll_occci": 0.26,                     # agrees with primary (1.3x)
        "chlorophyll_mosdac": 2.94,                    # 8.4x off
        "chlorophyll_mosdac_date": "2026-09-03",
        "chlorophyll_mosdac_pixel_km": 0.4,
        "chlorophyll_mosdac_ring_valid": 120,
        "chlorophyll_mosdac_ring_median": 0.41,        # neighbourhood sides with primary
    }
    res = satellite.analyze(snap)
    out = [f for f in res["findings"] if f["type"] == "chl_mosdac_check_outlier"]
    assert out, [f["type"] for f in res["findings"]]
    msg = out[0]["msg"]
    assert "outlier" in msg
    assert "HOT pixel" in msg                        # forensics: one bad pixel
    assert "Different dates" in msg                  # 09-01 vs 09-03 noted
    assert "NOT counted as an independent confirmation" in msg
    blob = " ".join(f["msg"] for f in res["findings"])
    assert "treat the fine structure as real" not in blob  # old blanket text removed


def test_satellite_mosdac_moderate_gap_keeps_resolution_story():
    """3–5x gap: finer-resolution explanation stays, but labeled UNRESOLVED."""
    snap = {
        "chlorophyll": 0.35, "chlorophyll_source": "NOAA",
        "chlorophyll_occci": 0.26,
        "chlorophyll_mosdac": 1.4,                     # exactly 4.0x
        "chlorophyll_mosdac_date": "2026-09-03",
    }
    res = satellite.analyze(snap)
    d = [f for f in res["findings"] if f["type"] == "chl_mosdac_check_disagree"]
    assert d, [f["type"] for f in res["findings"]]
    assert "1 km" in d[0]["msg"] and "UNRESOLVED" in d[0]["msg"]


def test_satellite_mosdac_large_gap_real_patch_detected():
    """Same 8x gap, but the granule's own neighbourhood is high too →
    forensics say 'real local patch' (not one bad pixel) — yet still an
    outlier finding that asks for verification."""
    snap = {
        "chlorophyll": 0.35, "chlorophyll_source": "NOAA",
        "chlorophyll_occci": 0.26,
        "chlorophyll_mosdac": 2.94, "chlorophyll_mosdac_date": "2026-09-03",
        "chlorophyll_mosdac_ring_valid": 120,
        "chlorophyll_mosdac_ring_median": 2.6,         # whole patch high
    }
    res = satellite.analyze(snap)
    out = [f for f in res["findings"] if f["type"] == "chl_mosdac_check_outlier"]
    assert out, [f["type"] for f in res["findings"]]
    assert "real local patch" in out[0]["msg"]
    assert "mosdac.gov.in" in out[0]["msg"]


def test_satellite_mosdac_uniform_area_rules_out_fine_structure():
    """The 10.12N/80.62E case: ring high AND wider area uniformly high →
    NOT fine structure; granule-level offset named as likelier."""
    snap = {
        "chlorophyll": 0.35, "chlorophyll_source": "NOAA",
        "chlorophyll_occci": 0.26,
        "chlorophyll_mosdac": 3.0, "chlorophyll_mosdac_date": "2026-09-03",
        "chlorophyll_mosdac_ring_valid": 289, "chlorophyll_mosdac_ring_median": 3.0,
        "chlorophyll_mosdac_area_median": 3.0,
    }
    msg = [f["msg"] for f in satellite.analyze(snap)["findings"]
           if f["type"] == "chl_mosdac_check_outlier"][0]
    assert "rules OUT fine coastal structure" in msg
    assert "granule-level offset" in msg


def test_satellite_mosdac_sharp_patch_area_normal_is_genuine_structure():
    """Ring high but wider area normal → fine structure is GENUINELY
    plausible (the only case where the resolution story survives)."""
    snap = {
        "chlorophyll": 0.35, "chlorophyll_source": "NOAA",
        "chlorophyll_occci": 0.26,
        "chlorophyll_mosdac": 2.9, "chlorophyll_mosdac_date": "2026-09-03",
        "chlorophyll_mosdac_ring_valid": 289, "chlorophyll_mosdac_ring_median": 2.6,
        "chlorophyll_mosdac_area_median": 0.40,
    }
    msg = [f["msg"] for f in satellite.analyze(snap)["findings"]
           if f["type"] == "chl_mosdac_check_outlier"][0]
    assert "wider ~80-pixel area reads normal" in msg
    assert "small sharp patch" in msg


def test_satellite_mosdac_cdom_case2_note():
    """CDOM readout at the pixel is surfaced as case-2 water evidence."""
    snap = {
        "chlorophyll": 0.35, "chlorophyll_source": "NOAA",
        "chlorophyll_mosdac": 3.0, "chlorophyll_mosdac_date": "2026-09-03",
        "chlorophyll_mosdac_ring_valid": 289, "chlorophyll_mosdac_ring_median": 2.8,
        "chlorophyll_mosdac_cdom_value": 0.42, "chlorophyll_mosdac_cdom_units": "m^-1",
    }
    msg = [f["msg"] for f in satellite.analyze(snap)["findings"]
           if f["type"] == "chl_mosdac_check_outlier"][0]
    assert "CDOM=0.42 m^-1" in msg and "Case-2" in msg


def test_satellite_mosdac_low_cdom_rules_out_turbidity_story():
    """The actual 10.12N/80.62E evidence: CDOM 0.0048 1/m = clear Case-1
    water, so the finding must say turbidity CANNOT explain the gap —
    not repeat the case-2 line uncritically."""
    snap = {
        "chlorophyll": 0.35, "chlorophyll_source": "NOAA",
        "chlorophyll_occci": 0.26,
        "chlorophyll_mosdac": 3.0, "chlorophyll_mosdac_date": "2026-09-03",
        "chlorophyll_mosdac_ring_valid": 289, "chlorophyll_mosdac_ring_median": 3.0,
        "chlorophyll_mosdac_area_median": 2.5,
        "chlorophyll_mosdac_cdom_value": 0.0048, "chlorophyll_mosdac_cdom_units": "1/m",
    }
    msg = [f["msg"] for f in satellite.analyze(snap)["findings"]
           if f["type"] == "chl_mosdac_check_outlier"][0]
    assert "CDOM=0.0048 1/m" in msg
    assert "Case-1" in msg and "cannot explain the gap" in msg
    assert "Case-2" not in msg


# ── Bug #2: marine risk must ESCALATE on the warning it quotes ────────

def _ocean_with_wave_caution():
    return {
        "agent": "ocean",
        "findings": [{
            "type": "wave_caution", "severity": "warn", "value": 2.74,
            "msg": "Max wave height 2.74m — rough seas, exercise caution.",
        }],
        "summary": "rough", "risk_level": "moderate",
    }


def test_marine_risk_escalates_on_wave_caution():
    """2.5 m+ waves (IMD small-craft caution) → at least 'moderate'."""
    res = marine_risk.analyze({}, agent_results=[_ocean_with_wave_caution()])
    assert res["risk_level"] in ("moderate", "high", "critical"), res
    assert res["risk_score"] >= 2


def test_marine_risk_calm_stays_low():
    ocean = {"agent": "ocean", "findings": [{
        "type": "wave_calm", "severity": "good", "value": 0.8, "msg": "calm"}],
        "summary": "calm", "risk_level": "low"}
    res = marine_risk.analyze({}, agent_results=[ocean])
    assert res["risk_level"] == "low"


def test_marine_risk_sees_gale_gusts():
    """A gale-gust finding from weather must matter to a boat."""
    wx = {"agent": "weather", "findings": [{
        "type": "gale_gusts", "severity": "warn", "value": 15.2,
        "msg": "Gale-force gusts to 15.2 m/s"}],
        "summary": "gusty", "risk_level": "moderate"}
    res = marine_risk.analyze({}, agent_results=[wx])
    assert res["risk_score"] >= 2
    assert res["risk_level"] != "low"


# ── Bug #1: gust escalation in the weather agent itself ────────────────

def test_weather_gale_gusts_escalate_risk(monkeypatch):
    """Sustained 5 m/s looking 'safe' + 16 m/s gusts → NOT safe."""
    import pipeline.ttlcache as ttlcache
    ttlcache.clear()  # don't let a cached fetch shadow the patch
    fake = {
        "daily": {
            "wind_speed_10m_max": [5.0],
            "wind_gusts_10m_max": [16.0],
            "precipitation_sum": [0.0],
            "weather_code": [1],
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [26.0],
        }
    }
    monkeypatch.setattr(weather, "_fetch", lambda *a, **k: fake)
    res = weather.analyze({"lat": 13.08, "lon": 80.28, "date": "2026-09-04"})
    types = [f["type"] for f in res["findings"]]
    assert "gale_gusts" in types
    assert res["risk_level"] in ("moderate", "high")
    # and the calm finding must quote the gust number, not hide it
    calm = next(f for f in res["findings"] if f["type"] == "wind_calm")
    assert "gusts 16.0" in calm["msg"]


def test_weather_light_gusts_stay_calm(monkeypatch):
    import pipeline.ttlcache as ttlcache
    ttlcache.clear()
    fake = {
        "daily": {
            "wind_speed_10m_max": [4.0],
            "wind_gusts_10m_max": [5.5],
            "precipitation_sum": [0.0],
            "weather_code": [0],
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [26.0],
        }
    }
    monkeypatch.setattr(weather, "_fetch", lambda *a, **k: fake)
    res = weather.analyze({"lat": 13.08, "lon": 80.28, "date": "2026-09-04"})
    assert res["risk_level"] == "low"


# ── Bug #1 (advisory card twin): gust band 28-34 kn must be CAUTION ────

def _patch_advisory_world(monkeypatch, *, gust_kn, wind_kn=10, wx_daily=None):
    """Neutral sea everywhere; only wind/gust varies.

    wx_daily: dict for pipeline.agents.weather.get_daily_summary — keeps
    the sky-condition rules deterministic (default: benign overcast)."""
    from pipeline import advisory
    from pipeline.agents import weather as wx_agent
    import pipeline.jtwc as jtwc
    import pipeline.ttlcache as ttlcache
    ttlcache.clear()
    monkeypatch.setattr(
        wx_agent, "get_daily_summary",
        lambda *a, **k: wx_daily if wx_daily is not None else
        {"wx_code": 2, "precip_probability_max": 10.0,
         "precipitation_sum": 0.0, "wind_max_ms": 4.0, "gust_max_ms": 6.0})
    monkeypatch.setattr(
        advisory, "zone_snapshot_cached",
        lambda *a, **k: {"lat": 13.0, "lon": 80.0, "sst_mean": 28.5,
                         "chlorophyll": 0.3,
                         "data_sources_used": [], "data_sources_failed": []})
    monkeypatch.setattr(
        advisory.fc, "get_point_forecast",
        lambda *a, **k: {
            "source": "mock",
            "now": {"wave_height_m": 0.8, "swell_height_m": 0.4,
                    "wind_kn": wind_kn, "gust_kn": gust_kn, "current_kn": 0.5,
                    "current_dir_deg": 90},
            "next24h": {"wave_max_m": 0.9, "gust_max_kn": gust_kn,
                        "rain_total_mm": 0.0},
            "next48h": {"wave_max_m": 0.9, "wind_max_kn": wind_kn,
                        "gust_max_kn": gust_kn},
        })
    monkeypatch.setattr(advisory.fc, "find_safe_window",
                        lambda *a, **k: {"found": False, "note": "mock"})
    monkeypatch.setattr(jtwc, "nearest_cyclone",
                        lambda *a, **k: {"found": False, "checked": True,
                                         "note": "No active tropical cyclone in the region right now."})
    monkeypatch.setattr(advisory.incois_pfz, "nearest_pfz",
                        lambda *a, **k: {"found": False})
    return advisory


def test_advisory_gusts_30kn_caution_not_comfortable(monkeypatch):
    """Chennai case: 10 kn sustained + 30 kn gusts was labelled
    'comfortable' while the UI tile glowed red-warn at >=28 kn."""
    advisory = _patch_advisory_world(monkeypatch, gust_kn=30)
    res = advisory.build_advisory(13.08, 80.28)
    gust_reason = next(
        (r for r in res["reasons"] if r["code"] == "gusts_high"), None)
    assert gust_reason is not None, [r["code"] for r in res["reasons"]]
    assert gust_reason["severity"] == "caution"
    assert res["verdict"] == "caution"


def test_advisory_quotes_gusts_even_when_calm(monkeypatch):
    """Below the caution band the info line still quotes BOTH numbers."""
    advisory = _patch_advisory_world(monkeypatch, gust_kn=22)
    res = advisory.build_advisory(13.08, 80.28)
    wind_reason = next(r for r in res["reasons"] if r["code"] == "wind_ok")
    assert "gusts 22" in wind_reason["msg"]
    assert "comfortable" not in wind_reason["msg"] or "sustained" in wind_reason["msg"]


# ── Now-vs-Peak labelling (review round 3) ─────────────────────────────

def test_ocean_uses_48h_peak_and_labels_both_numbers():
    """Reason panel must quote the 48h peak + 'now', and mark the 30-day
    window max as history — not as a silent contradiction."""
    from pipeline.agents import ocean
    snap = {"sst_mean": 28.0, "wave_max": 4.2,
            "wave_now_m": 1.48, "wave_peak_48h_m": 2.4}
    res = ocean.analyze(snap)
    calm = next(f for f in res["findings"] if f["type"] == "wave_calm")
    assert "2.4 m" in calm["msg"] and "1.48 m now" in calm["msg"]
    hist = next(f for f in res["findings"] if f["type"] == "wave_recent_window")
    assert "Past ~30-day" in hist["msg"] and "NOT today" in hist["msg"]
    assert res["risk_level"] == "low"


def test_ocean_without_forecast_labels_window_max_honestly():
    from pipeline.agents import ocean
    res = ocean.analyze({"sst_mean": 28.0, "wave_max": 3.1})
    w = next(f for f in res["findings"] if f["type"] == "wave_caution")
    assert "past ~30 days" in w["msg"]
    assert res["risk_level"] == "moderate"


def test_marine_risk_escalates_on_fresh_breeze():
    """The Vizag case: weather quoted 'Fresh breeze 10.2 m/s, exercise
    caution' but Marine Risk stayed LOW. Wind WARNs must count like wave
    WARNs."""
    wx = {"agent": "weather", "findings": [{
        "type": "fresh_breeze", "severity": "warn", "value": 10.2,
        "msg": "Fresh breeze 10.2 m/s (Beaufort 5). Exercise caution."}],
        "summary": "breezy", "risk_level": "moderate"}
    res = marine_risk.analyze({}, agent_results=[wx])
    assert res["risk_level"] != "low"
    assert res["risk_score"] >= 2


def test_advisory_wind_reason_labels_peak_and_now(monkeypatch):
    """'Wind 12 kn, gusts 17 kn' (tile) vs 'Wind up to 25 kn (gusts 32 kn)'
    (text) read as a contradiction; the text must now say which is peak
    and which is now."""
    advisory = _patch_advisory_world(monkeypatch, gust_kn=17, wind_kn=12)
    monkeypatch.setattr(
        advisory.fc, "get_point_forecast",
        lambda *a, **k: {
            "source": "mock",
            "now": {"wave_height_m": 1.48, "swell_height_m": 0.4,
                    "wind_kn": 12, "gust_kn": 17, "current_kn": 0.5,
                    "current_dir_deg": 90},
            "next24h": {"wave_max_m": 1.6, "gust_max_kn": 20,
                        "rain_total_mm": 0.0},
            "next48h": {"wave_max_m": 1.6, "wind_max_kn": 25,
                        "gust_max_kn": 32},
        })
    res = advisory.build_advisory(15.16, 82.09)
    r = next(r for r in res["reasons"] if r["code"] == "wind_strong")
    assert r["severity"] == "caution"
    assert "peak" in r["msg"] and "Right now: 12 kn" in r["msg"]


def test_advisory_flags_unusually_strong_current(monkeypatch):
    advisory = _patch_advisory_world(monkeypatch, gust_kn=10)
    monkeypatch.setattr(
        advisory.fc, "get_point_forecast",
        lambda *a, **k: {
            "source": "mock",
            "now": {"wave_height_m": 0.8, "swell_height_m": 0.4,
                    "wind_kn": 10, "gust_kn": 10, "current_kn": 6.03,
                    "current_dir_deg": 110},
            "next24h": {"wave_max_m": 0.9, "gust_max_kn": 10,
                        "rain_total_mm": 0.0},
            "next48h": {"wave_max_m": 0.9, "wind_max_kn": 10,
                        "gust_max_kn": 10},
        })
    res = advisory.build_advisory(15.16, 82.09)
    codes = [r["code"] for r in res["reasons"]]
    assert "current_strong" in codes


# ── Review round-6: advisory must see the sky, not just wind/waves ─────
# External reviewer: 15.42N/81.85E had a VERIFIED thunderstorm-with-hail
# day (WMO 96, 85% rain chance). Weather agent + Marine Risk both said
# MODERATE, but the Advisory card said "✅ GO" with no storm bullet —
# opposite safety verdicts on the two most user-facing surfaces.

def test_advisory_thunderstorm_hail_forces_caution_not_go(monkeypatch):
    advisory = _patch_advisory_world(
        monkeypatch, gust_kn=14, wind_kn=11,
        wx_daily={"wx_code": 96, "precip_probability_max": 85.0,
                  "precipitation_sum": 12.0})
    res = advisory.build_advisory(15.42, 81.85)
    assert res["verdict"] == "caution", res["reasons"]
    blob = " ".join(r["msg"] for r in res["reasons"])
    assert "HAIL" in blob and "WMO 96" in blob and "85%" in blob


def test_advisory_heavy_hail_forces_no_go(monkeypatch):
    advisory = _patch_advisory_world(
        monkeypatch, gust_kn=14, wind_kn=11,
        wx_daily={"wx_code": 99, "precip_probability_max": 90.0})
    res = advisory.build_advisory(15.42, 81.85)
    assert res["verdict"] == "no_go", res["reasons"]
    assert "HEAVY HAIL" in " ".join(r["msg"] for r in res["reasons"])


def test_advisory_plain_thunderstorm_forces_caution(monkeypatch):
    advisory = _patch_advisory_world(
        monkeypatch, gust_kn=14, wind_kn=11,
        wx_daily={"wx_code": 95, "precip_probability_max": 80.0})
    res = advisory.build_advisory(15.42, 81.85)
    assert res["verdict"] == "caution"
    assert "Thunderstorm" in " ".join(r["msg"] for r in res["reasons"])


def test_advisory_high_rain_chance_gets_bullet_without_changing_go(monkeypatch):
    """85% rain chance alone (no storm code) → still GO, but the 'why'
    list must now MENTION the rain — the old card never did."""
    advisory = _patch_advisory_world(
        monkeypatch, gust_kn=14, wind_kn=11,
        wx_daily={"wx_code": 2, "precip_probability_max": 85.0})
    res = advisory.build_advisory(15.42, 81.85)
    assert res["verdict"] == "go"
    blob = " ".join(r["msg"] for r in res["reasons"])
    assert "Rain chance is high today (85%)" in blob


def test_advisory_storm_beats_calm_wind_and_waves(monkeypatch):
    """Storm floor works even when every marine number looks perfect —
    the exact disagreement the reviewer screenshotted."""
    advisory = _patch_advisory_world(
        monkeypatch, gust_kn=10, wind_kn=8,
        wx_daily={"wx_code": 96, "precip_probability_max": 85.0})
    res = advisory.build_advisory(15.42, 81.85)
    assert res["verdict"] == "caution"
    codes = [r["code"] for r in res["reasons"]]
    assert "hail_storm" in codes and "waves_calm" in codes and "wind_ok" in codes


# ── Centralized risk-tag rule (review round 4) ─────────────────────────

def test_central_rule_all_info_with_data_is_low():
    from pipeline.agents import risk_from_findings
    fs = [{"severity": "info"}, {"severity": "info"}]
    assert risk_from_findings(fs, has_data=True) == "low"
    assert risk_from_findings(fs, has_data=False) == "unknown"
    assert risk_from_findings([{"severity": "warn"}], has_data=True) == "moderate"
    assert risk_from_findings([{"severity": "high"}], has_data=True) == "high"


def test_weather_all_info_day_is_low_not_no_data(monkeypatch, ):
    """Reviewer's 9.08N/82.60E case: moderate breeze + light showers +
    temp — all info-tier findings, yet the chip said 'no data'."""
    import pipeline.ttlcache as ttlcache
    ttlcache.clear()
    from pipeline.agents import weather
    fake = {
        "daily": {
            "wind_speed_10m_max": [8.4],
            "wind_gusts_10m_max": [10.1],
            "precipitation_sum": [5.6],
            "weather_code": [80],  # light showers — info tier
            "temperature_2m_max": [30.0],
            "temperature_2m_min": [27.0],
        }
    }
    monkeypatch.setattr(weather, "_fetch", lambda *a, **k: fake)
    res = weather.analyze({"lat": 9.08, "lon": 82.60, "date": "2026-09-05"})
    assert res["risk_level"] == "low", res
    # and the daily-max value must be LABELLED as such
    wind_f = next(f for f in res["findings"] if f["type"] == "wind_moderate")
    assert "max today" in wind_f["msg"]
    cond_f = next(f for f in res["findings"] if f["type"] == "weather_condition")
    assert "WMO 80" in cond_f["msg"] and "dominant" in cond_f["msg"]


def test_ocean_all_info_day_is_low_not_unknown():
    from pipeline.agents import ocean
    res = ocean.analyze({"sst_mean": 25.0})  # acceptable → info only
    assert res["risk_level"] == "low"
