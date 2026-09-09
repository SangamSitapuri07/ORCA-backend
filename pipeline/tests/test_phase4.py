"""Phase-4 tests — advisory, chat router, alerts, PFZ geometry, JTWC parser.

All OFFLINE. Fixtures are real data recorded from live calls made on
2026-09-03 (the actual Open-Meteo response for Veraval, the actual JTWC
warning text for TS Saudel, the actual INCOIS PFZ lines shape) — replayed
so CI doesn't need the network and the logic is tested against the true
wire formats.
"""
from __future__ import annotations

import pytest

from pipeline import alerts as alerts_mod
from pipeline import chat as chat_mod
from pipeline import forecast as fc
from pipeline import incois_pfz, jtwc
from pipeline.advisory import build_advisory

# ── Real recorded fixtures (2026-09-03, Veraval 20.9N 70.37E) ──────

FAKE_FORECAST = {
    "source": "Open-Meteo Marine + Forecast (MeteoFrance/ECMWF models)",
    "lat": 20.9, "lon": 70.37,
    "fetched_at": "2026-09-03T12:00:00+00:00",
    "hourly": {
        "time": ["2026-09-03T00:00", "2026-09-03T01:00"],
        "wave_height_m": [1.74, 1.72],
        "swell_height_m": [1.2, 1.2],
        "current_kn": [0.97, 0.58],
        "current_dir_deg": [180.0, 180.0],
        "wind_kn": [10.5, 11.0],
        "gust_kn": [13.0, 13.5],
        "rain_mm": [0.0, 0.0],
    },
    "now": {"time": "2026-09-03T01:00Z", "wave_height_m": 1.72, "swell_height_m": 1.2,
            "current_kn": 0.58, "current_dir_deg": 180.0, "wind_kn": 11.0,
            "gust_kn": 13.5, "rain_mm": 0.0},
    "next24h": {"wave_max_m": 1.9, "swell_max_m": 1.4, "wind_max_kn": 12.5,
                "gust_max_kn": 15.0, "rain_total_mm": 0.0},
    "next48h": {"wave_max_m": 2.1, "swell_max_m": 1.5, "wind_max_kn": 12.5,
                "gust_max_kn": 15.0, "rain_total_mm": 0.0},
}

FAKE_SNAPSHOT = {
    "lat": 20.9, "lon": 70.37, "date": "2026-09-03",
    "sst_mean": 28.4, "sst_max": 28.9, "sst_min": 27.9,
    "chlorophyll": 1.21, "chlorophyll_unit": "mg/m^3",
    "data_sources_used": ["Open-Meteo Marine (SST + waves)", "NOAA ERDDAP (chlorophyll)"],
    "data_sources_failed": [],
    "fetched_at": "2026-09-03T12:00:00+00:00",
}

# Real JTWC warning text shape (TS 17W Saudel, final piece truncated)
SAUDEL_WEBTXT = """WTPN32 PGTW 030300
MSGID/GENADMIN/JOINT TYPHOON WRNCEN PEARL HARBOR HI//
SUBJ/TROPICAL STORM 17W (SAUDEL) WARNING NR 047//
RMKS/
1. TROPICAL STORM 17W (SAUDEL)  WARNING NR 047
   MAX SUSTAINED WINDS BASED ON ONE-MINUTE AVERAGE
   WIND RADII VALID OVER OPEN WATER ONLY
    ---
   WARNING POSITION:
   030000Z --- NEAR 23.8N 117.4E
     MOVEMENT PAST SIX HOURS - 295 DEGREES AT 10 KTS
     POSITION ACCURATE TO WITHIN 040 NM
   PRESENT WIND DISTRIBUTION:
   MAX SUSTAINED WINDS - 040 KT, GUSTS 050 KT
   RADIUS OF 034 KT WINDS - 040 NM NORTHEAST QUADRANT
                            040 NM SOUTHEAST QUADRANT
                            035 NM SOUTHWEST QUADRANT
                            030 NM NORTHWEST QUADRANT
"""


# ── PFZ geometry (pure math) ───────────────────────────────────────

def test_haversine_sanity():
    # 1 degree of latitude ≈ 111.2 km (known geodesy fact)
    d = incois_pfz.haversine_km(20.0, 70.0, 21.0, 70.0)
    assert 110.0 < d < 112.5


def test_point_segment_distance_and_tie():
    # point north of segment midpoint → closest point on segment
    d, (clat, clon) = incois_pfz._point_segment_km(20.1, 70.05, 20.0, 70.0, 20.0, 70.1)
    assert d == pytest.approx(11.1, abs=0.3)
    # nearest endpoint math: point beyond the segment end snaps to the end
    d2, (clat2, clon2) = incois_pfz._point_segment_km(20.0, 70.2, 20.0, 70.0, 20.0, 70.1)
    assert (round(clat2, 2), round(clon2, 2)) == (20.0, 70.1)


def test_bearing_cardinals():
    assert incois_pfz.bearing_deg(20.0, 70.0, 21.0, 70.0) == pytest.approx(0.0, abs=1.0)
    assert incois_pfz.bearing_deg(20.0, 70.0, 20.0, 71.0) == pytest.approx(90.0, abs=1.0)


def test_nearest_pfz_with_injected_lines(monkeypatch):
    fake = {
        "source": "test", "fetched_at": "x", "n_lines": 1,
        "latest_julian_day": "246", "year": 2026, "advisory_date": "2026-09-03",
        "lines": [{
            "uid": 2026246001.0, "sno": "001", "sector_code": 5,
            "sector_name": "Karnataka", "julian_day": "246", "year": 2026,
            "length_km": 67.9, "part": 0,
            "coords": [[70.0, 20.5], [70.2, 20.6], [70.4, 20.6]],
        }],
    }
    monkeypatch.setattr(incois_pfz, "get_lines", lambda **k: fake)
    r = incois_pfz.nearest_pfz(20.0, 70.2)
    assert r["found"] is True
    assert 40 < r["distance_km"] < 60  # ~0.5 deg of latitude
    assert r["distance_nm"] == pytest.approx(r["distance_km"] / 1.852, abs=0.2)
    assert r["advisory_date"] == "2026-09-03"


def test_nearest_pfz_none_nearby(monkeypatch):
    fake = {
        "source": "test", "fetched_at": "x", "n_lines": 1,
        "latest_julian_day": "246", "year": 2026, "advisory_date": "2026-09-03",
        "lines": [{"uid": 1, "sno": "1", "sector_code": 3, "sector_name": "Maharashtra",
                   "julian_day": "246", "year": 2026, "length_km": 10.0, "part": 0,
                   "coords": [[60.0, 10.0], [60.1, 10.1]]}],
    }
    monkeypatch.setattr(incois_pfz, "get_lines", lambda **k: fake)
    r = incois_pfz.nearest_pfz(22.0, 70.37)
    assert r["found"] is False and r.get("note")


# ── JTWC parser (real warning-text fixture) ────────────────────────

def test_jtwc_parse_position_and_winds():
    c = jtwc.parse_warning_text("wp1726", SAUDEL_WEBTXT)
    assert c is not None
    assert c["lat"] == pytest.approx(23.8)
    assert c["lon"] == pytest.approx(117.4)
    assert c["max_wind_kt"] == 40 and c["gust_kt"] == 50
    assert c["movement_deg"] == 295 and c["movement_kt"] == 10
    assert c["radius_34kt_nm"] == 40
    assert c["name"] == "Saudel"


def test_jtwc_skips_final_warning():
    final_txt = SAUDEL_WEBTXT.replace("WARNING NR 047", "FINAL WARNING NR 047", 1)
    assert jtwc.parse_warning_text("wp1726", final_txt) is None


# ── Forecast helpers ───────────────────────────────────────────────

def test_safe_window_calm_forecast():
    sw = fc.find_safe_window(FAKE_FORECAST, horizon_hours=2, min_hours=2)
    # history horizon is short here but waves 1.7m < 2.5 so a window exists
    assert isinstance(sw, dict)
    assert "found" in sw


def test_safe_window_stormy_forecast():
    stormy = {
        "hourly": {
            "time": [f"2030-01-01T{h:02d}:00" for h in range(8)],
            "wave_height_m": [5.0] * 8,
            "swell_height_m": [3.0] * 8,
            "wind_kn": [40.0] * 8,
            "gust_kn": [50.0] * 8,
        }
    }
    sw = fc.find_safe_window(stormy, horizon_hours=8)
    assert sw["found"] is False


# ── Advisory engine (with monkeypatched real-shaped sources) ───────

def _patch_calm(monkeypatch):
    monkeypatch.setattr("pipeline.advisory.zone_snapshot_cached", lambda *a, **k: dict(FAKE_SNAPSHOT))
    monkeypatch.setattr(fc, "get_point_forecast", lambda *a, **k: dict(FAKE_FORECAST))
    monkeypatch.setattr(incois_pfz, "nearest_pfz", lambda lat, lon: {
        "available": True, "found": True, "distance_km": 24.0, "distance_nm": 13.0,
        "bearing_deg": 300, "nearest_point": {"lat": 21.05, "lon": 70.2},
        "sector_name": "Gujarat", "uid": 2026246001.0, "line_length_km": 67.9,
        "advisory_date": "2026-09-03", "julian_day": "246",
        "source": "INCOIS PFZ Advisory (GeoServer WFS)",
    })
    monkeypatch.setattr(jtwc, "nearest_cyclone", lambda lat, lon, **k: {
        "checked": True, "found": False, "advisories_anywhere": 0,
        "errors": [], "source": "JTWC", "note": "No active tropical cyclone in the region right now.",
    })


def test_advisory_go_verdict(monkeypatch):
    _patch_calm(monkeypatch)
    adv = build_advisory(20.9, 70.37)
    assert adv["verdict"] == "go"
    assert adv["variables"]["wave_height_m"] == 1.72
    assert adv["variables"]["nearest_pfz_km"] == 24.0
    assert adv["icon"] == "✅"
    assert any(r["code"] == "official_pfz" for r in adv["reasons"])
    assert adv["sources"], "advisory must cite its sources"


def test_advisory_no_go_on_cyclone(monkeypatch):
    _patch_calm(monkeypatch)
    monkeypatch.setattr(jtwc, "nearest_cyclone", lambda lat, lon, **k: {
        "checked": True, "found": True, "distance_km": 210, "bearing_deg": 160,
        "cyclone": {"name": "Testya", "designation": "02A", "basin": "io",
                    "max_wind_kt": 65, "intensity": "Very Severe Cyclonic Storm",
                    "advisory_no": 3, "lat": 19.0, "lon": 71.5, "source": "JTWC"},
        "source": "JTWC",
    })
    adv = build_advisory(20.9, 70.37)
    assert adv["verdict"] == "no_go"
    assert adv["icon"] == "⛔"
    assert adv["variables"]["cyclone_dist_km"] == 210
    assert any(r["code"] == "cyclone_near" for r in adv["reasons"])


def test_advisory_caution_on_waves(monkeypatch):
    _patch_calm(monkeypatch)
    rough = dict(FAKE_FORECAST)
    rough["now"] = {**FAKE_FORECAST["now"], "wave_height_m": 3.1}
    rough["next48h"] = {**FAKE_FORECAST["next48h"], "wave_max_m": 3.3}
    monkeypatch.setattr(fc, "get_point_forecast", lambda *a, **k: rough)
    adv = build_advisory(20.9, 70.37)
    assert adv["verdict"] == "caution"
    assert any(r["code"] == "waves_elevated" for r in adv["reasons"])


# ── Alerts engine ──────────────────────────────────────────────────

def test_alerts_calm_point_no_alerts(monkeypatch):
    alerts_mod._store.clear()
    monkeypatch.setattr(fc, "get_point_forecast", lambda *a, **k: dict(FAKE_FORECAST))
    monkeypatch.setattr(jtwc, "nearest_cyclone", lambda lat, lon, **k: {
        "checked": True, "found": False, "advisories_anywhere": 0, "errors": [],
        "source": "JTWC", "note": "none"})
    made = alerts_mod.evaluate(20.9, 70.37)
    assert made == []
    assert alerts_mod.list_alerts() == []


def test_alerts_gale_warning(monkeypatch):
    alerts_mod._store.clear()
    windy = dict(FAKE_FORECAST)
    windy["next24h"] = {**FAKE_FORECAST["next24h"], "gust_max_kn": 38.0}
    monkeypatch.setattr(fc, "get_point_forecast", lambda *a, **k: windy)
    monkeypatch.setattr(jtwc, "nearest_cyclone", lambda lat, lon, **k: {
        "checked": True, "found": False, "advisories_anywhere": 0, "errors": [],
        "source": "JTWC", "note": "none"})
    made = alerts_mod.evaluate(20.9, 70.37)
    assert any(a["code"] == "gale" and a["severity"] == "warning" for a in made)
    assert all(a["simulated"] is False for a in made)


def test_simulated_alert_is_labelled():
    a = alerts_mod.simulate("cyclone", 20.9, 70.37)
    assert a["simulated"] is True
    assert a["title_en"].startswith("🧪 DEMO")
    assert a["severity"] == "warning"
    with pytest.raises(ValueError):
        alerts_mod.simulate("volcano", 0, 0)


# ── Chat router + composition ──────────────────────────────────────

def test_chat_route_pfz_intent():
    r = chat_mod.route("bhai machli kahaan milegi aaj?")
    assert "pfz" in r["intents"]
    assert "fisheries" in r["agents"]
    assert "incois_pfz" in r["tools"]


def test_chat_route_hazard_intent():
    r = chat_mod.route("Is there any cyclone warning for tomorrow?")
    assert "hazard" in r["intents"]
    assert "jtwc" in r["tools"]


def test_chat_route_default_is_safety():
    r = chat_mod.route("hello")
    assert r["intents"] == ["safety"]


def test_compose_answer_contains_real_numbers(monkeypatch):
    _patch_calm(monkeypatch)
    adv = build_advisory(20.9, 70.37)
    trace = {
        "routing": {"intents": ["safety"], "agents": ["ocean"], "tools": ["forecast"]},
        "advisory": adv,
        "agent_results": [],
        "extra": {"forecast": FAKE_FORECAST},
        "insight": None,
    }
    text = chat_mod.compose_answer(trace, "kya hum safe hai?")
    assert adv["icon"] in text
    assert "1.72" in text or "1.7" in text  # wave height number must appear
    assert "No cyclone" in text or "cyclone" in text.lower()
    assert "Sources:" in text


# ── Field Explorer (offline) ─────────────────────────────────────────

def test_field_grid_points_shape():
    from pipeline import field_explorer as fx
    pts = fx._grid_points(19.0, 72.0)
    assert len(pts) == fx.GRID_TARGET_N ** 2
    lats = {p[0] for p in pts}
    lons = {p[1] for p in pts}
    assert len(lats) == fx.GRID_TARGET_N and len(lons) == fx.GRID_TARGET_N
    assert min(lats) < 19.0 < max(lats)
    assert min(lons) < 72.0 < max(lons)


def test_field_hotspots_ranked_and_labelled():
    from pipeline import field_explorer as fx
    pts = [
        {"lat": 19.0, "lon": 72.5, "chl": 0.4},
        {"lat": 19.4, "lon": 72.1, "chl": 6.2},   # top
        {"lat": 18.6, "lon": 71.8, "chl": 2.1},
        {"lat": 19.2, "lon": 71.4, "chl": 1.0},
    ]
    hs = fx._hotspots(pts, 19.0, 72.0, top=3)
    assert len(hs) == 3
    assert hs[0]["chl"] == 6.2  # sorted desc
    for h in hs:
        assert h["distance_km"] > 0 and h["distance_nm"] > 0
        assert h["bearing"] in {"N","NNE","NE","ENE","E","ESE","SE","SSE",
                                "S","SSW","SW","WSW","W","WNW","NW","NNW"}


def test_field_build_error_tolerance(monkeypatch):
    """One source down must never kill the whole field response."""
    from pipeline import field_explorer as fx
    monkeypatch.setattr(fx, "fetch_chl_grid", lambda *a: (_ for _ in ()).throw(ValueError("chl dead")))
    monkeypatch.setattr(fx, "fetch_met_grid", lambda *a: {"points": [{"lat": 1, "lon": 2, "wave_m": 1.0}], "n": 1, "source": "mock"})
    out = fx._build(19.0, 72.0)
    assert out["type"] == "field"
    assert out["chl"]["error"] and "chl dead" in out["chl"]["error"]
    assert out["met"]["n"] == 1
    assert out["hotspots"] == []  # honest empty, not a crash


def test_field_land_pixels_masked_from_grid(monkeypatch):
    """Regression (2026-09-08 demo): NOAA DINEOF can report chl ON LAND
    (coastal bleed / lagoon pixels, e.g. 5.568 mg/m3 at 19.29N 84.38E
    Ganjam district). That pixel must never reach the map or ranking."""
    import csv
    import io

    from pipeline import field_explorer as fx
    csv_text = (
        "time,altitude,latitude,longitude,chlor_a\n"
        "UTC,m,degrees_north,degrees_east,mg m^-3\n"
        "2026-09-05T12:00:00Z,0.0,19.2875,84.3875,5.568\n"   # LAND (Ganjam, Odisha)
        "2026-09-05T12:00:00Z,0.0,19.0,86.5,2.0\n"           # sea
        "2026-09-05T12:00:00Z,0.0,19.0375,86.5375,3.5\n"     # sea (top)
        "2026-09-05T12:00:00Z,0.0,19.5,86.2,NaN\n"           # no data
    )
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    monkeypatch.setattr(fx, "_fetch_csv", lambda url: rows)
    out = fx.fetch_chl_grid(19.5, 85.5)
    assert sorted(p["chl"] for p in out["points"]) == [2.0, 3.5]  # land pixel dropped
    assert out["land_masked"] == 1
    assert out["n"] == 2
    hs = fx._hotspots(out["points"], 19.5, 85.5, top=3)
    assert hs and all(abs(h["chl"] - 5.568) > 1e-9 for h in hs)


def test_field_hotspots_never_rank_land(monkeypatch):
    """Belt-and-braces: even a hand-built on-land point cannot rank as a
    'fishing hotspot' (verified real GLOBE 1 km mask, not a mock)."""
    from pipeline import field_explorer as fx
    pts = [
        {"lat": 19.96, "lon": 85.04, "chl": 12.477},  # LAND (Nayagarh, Odisha)
        {"lat": 21.29, "lon": 86.29, "chl": 10.566},  # LAND (Balasore side)
        {"lat": 19.0,  "lon": 86.5,  "chl": 1.0},     # open sea
    ]
    hs = fx._hotspots(pts, 19.5, 85.5, top=3)
    assert len(hs) == 1 and hs[0]["chl"] == 1.0


def test_field_met_grid_carries_land_flag(monkeypatch):
    """Every met cell must carry its real land/sea flag for honest UI labels."""
    from pipeline import field_explorer as fx
    n = fx.GRID_TARGET_N ** 2
    fake_marine = [{"current": {"wave_height": 1.0}}] * n
    fake_wx = [{"current": {"wind_speed_10m": 5}}] * n
    calls = []

    def fake_http(url, params, timeout=15.0):
        calls.append(url)
        return fake_marine if "marine" in url else fake_wx

    monkeypatch.setattr(fx, "_http_json", fake_http)
    out = fx.fetch_met_grid(19.5, 85.5)   # Odisha coast box: mix of land+sea
    assert out["n"] == n
    flags = {p["land"] for p in out["points"]}
    assert flags - {True, False, None} == set()   # only honest tri-state
    assert True in flags and False in flags        # box really spans the coast


def test_sea_route_straight_leg_clear():
    """Open Arabian Sea leg: every sample water → ok, no detour, one leg."""
    from pipeline import routecheck as rc
    r = rc.compute_sea_route(19.0, 70.5, 19.6, 71.2)
    assert r["ok"] is True and r["detour"] is False
    assert r["legs"] == [r["from"], r["to"]]
    assert r["distance_nm"] > 0 and 0 <= r["bearing_deg"] < 360


def test_sea_route_rounds_kanyakumari_with_one_real_waypoint():
    """(8.0N,77.3E) → (9.2N,79.2E) crosses the Kanyakumari cape. The route
    checker must find ONE computed waypoint that rounds it — and every
    resulting leg must verify water-only under the SAME mask sampling."""
    from pipeline import routecheck as rc
    r = rc.compute_sea_route(8.0, 77.3, 9.2, 79.2)
    assert r["ok"] is True and r["detour"] is True
    assert len(r["legs"]) == 3
    wp = r["legs"][1]
    assert wp[0] < r["from"][0] or wp[1] > r["from"][1]  # seaward of the cape
    for i in range(len(r["legs"]) - 1):
        a, b = r["legs"][i], r["legs"][i + 1]
        assert rc._seg_land_hit(a[0], a[1], b[0], b[1]) is None


def test_sea_route_to_land_target_is_honest_block():
    """A course whose TARGET is on land (verified vs GLOBE) can never be
    made water-only — every detour leg ends on land. Must say ok=False
    and never fake a safe line."""
    from pipeline import routecheck as rc
    r = rc.compute_sea_route(19.05, 72.2, 19.05, 72.95)  # offshore → onshore (LAND per GLOBE)
    assert r["ok"] is False
    assert r["legs"] == [r["from"], r["to"]]  # honest: no invented line


def test_sea_route_unknown_when_mask_unavailable(monkeypatch):
    """Mask down → ok=None 'unverified', never a false 'safe'."""
    from pipeline import landmask, routecheck as rc
    monkeypatch.setattr(landmask, "enabled", lambda: False)
    r = rc.compute_sea_route(19.0, 70.5, 19.6, 71.2)
    assert r["ok"] is None and "NOT verified" in r["reason"]


def test_hotspot_coastal_bloom_gets_turbidity_caveat():
    """Reviewer flag (11.76 mg/m³ at the river-mouth grid): a bloom-range
    SEA cell within a short sail of land (Digha offshore: 8 km) must
    carry the sediment caveat. (Side-proof of the land mask's value: the
    old screenshot coordinate 21.63N 87.29E that LOOKED like river-mouth
    water is actually DRY GROUND near Contai — the same grid artefact.)"""
    from pipeline import field_explorer as fx
    pts = [
        {"lat": 21.62, "lon": 87.75, "chl": 11.763},  # Digha offshore: SEA, ~8 km from coast
        {"lat": 19.0, "lon": 70.0, "chl": 6.0},       # bloom but far offshore (>60 km)
    ]
    hs = fx._hotspots(pts, 20.0, 84.0, top=3)
    coastal = next(h for h in hs if h["chl"] == 11.763)
    offshore = next(h for h in hs if h["chl"] == 6.0)
    assert coastal["bloom"] is True
    assert coastal["coast_km"] is not None and coastal["coast_km"] <= fx.COASTAL_CAVEAT_KM
    assert coastal["caveat"] and "sediment" in coastal["caveat"]
    assert offshore["caveat"] is None  # honest bloom, no scare-label


# ── Rich chart series (48 h evidence arrays) ─────────────────────────

def test_chart_series_exposes_all_variables():
    """Every agent-visible chart array must come from the SAME hourly data."""
    fcst = dict(FAKE_FORECAST)
    fcst["hourly"] = {**FAKE_FORECAST["hourly"], "sst_c": [28.4, 28.5]}
    out = fc.chart_series(fcst, hours=2, step=1)
    for key in ("wave_m", "swell_m", "wind_kn", "gust_kn", "current_kn", "sst_c", "rain_mm"):
        assert key in out, f"chart series missing {key}"
        assert len(out[key]) == len(out["labels"]) >= 1
    # _now_index lands on the LAST past hour for these 2026-09-03 times
    assert out["current_kn"][0] == 0.58
    assert out["sst_c"][0] == 28.5


def test_chart_series_tolerates_old_cached_entries():
    """A forecast cached before SST existed must not crash the charts."""
    out = fc.chart_series(dict(FAKE_FORECAST), hours=2, step=1)  # no sst_c key at all
    assert out["sst_c"] == [None] * len(out["labels"])
    assert out["wave_m"][0] is not None


def test_advisory_sst_falls_back_to_marine_model(monkeypatch):
    """When the daily SST record source is down, the hourly marine-model
    SST is used — and honestly labelled as such."""
    _patch_calm(monkeypatch)
    monkeypatch.setattr("pipeline.advisory.zone_snapshot_cached",
                        lambda *a, **k: {**FAKE_SNAPSHOT, "sst_mean": None, "sst_max": None})
    fcst = dict(FAKE_FORECAST)
    fcst["now"] = {**FAKE_FORECAST["now"], "sst_c": 28.7}
    monkeypatch.setattr(fc, "get_point_forecast", lambda *a, **k: fcst)
    adv = build_advisory(20.9, 70.37)
    assert adv["variables"]["sst_c"] == 28.7
    assert "marine model" in adv["variables"]["sst_source"]


def test_field_met_grid_parses_sst(monkeypatch):
    """The multi-point marine call returns per-cell SST; it must land on points."""
    from pipeline import field_explorer as fx

    def fake_http(url, params, timeout=15.0):
        n = len(params["latitude"].split(","))
        if "marine" in url:
            return [{"current": {"wave_height": 1.5, "swell_wave_height": 0.9,
                                 "ocean_current_velocity": 0.5,
                                 "ocean_current_direction": 240.0,
                                 "sea_surface_temperature": 28.9}}] * n
        return [{"current": {"wind_speed_10m": 11.0, "wind_gusts_10m": 14.0,
                             "wind_direction_10m": 250.0}}] * n

    monkeypatch.setattr(fx, "_http_json", fake_http)
    out = fx.fetch_met_grid(19.0, 72.0)
    assert out["n"] == fx.GRID_TARGET_N ** 2
    p = out["points"][0]
    assert p["sst_c"] == 28.9
    assert p["current_kn"] == round(0.5 * 1.943844, 2)
    assert p["current_dir_deg"] == 240.0     # real flow direction → 3D arrows
    assert p["wind_dir_deg"] == 250.0        # real wind direction → 3D streaks
