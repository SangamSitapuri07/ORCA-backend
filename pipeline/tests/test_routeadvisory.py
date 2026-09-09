"""Transit-verdict logic tests — pure functions only, no network.

The live fetch path is exercised by the existing forecast tests; here
we pin the SAMPLING geometry (so the app and docs agree on where the
numbers came from) and the VERDICT REDUCTION (so 'nogo' really means
the advisory thresholds were crossed, not invented)."""
from pipeline.routeadvisory import (
    _point_state, _reduce_verdict, _sample_points,
    GUST_DANGER_KN, WAVE_CAUTION_M, WAVE_DANGER_M,
)


def _pf(wave=1.0, wave48=1.4, wind=8.0, wind48=12.0, gust48=16.0,
        current=0.6, sst=29.0):
    return {
        "source": "Open-Meteo marine + forecast",
        "now": {"wave_height_m": wave, "wind_kn": wind,
                "current_kn": current, "sst_c": sst},
        "next48h": {"wave_max_m": wave48, "wind_max_kn": wind48,
                    "gust_max_kn": gust48},
    }


# ── sampling ────────────────────────────────────────────────────────

def test_straight_90km_samples_every_30km():
    pts = _sample_points([[19.0, 72.0], [19.0, 72.85]])  # ~90 km E-W
    kms = [p["sail_km"] for p in pts]
    assert kms[0] == 0.0 and kms[-1] > 80          # start & end pinned
    assert all(kms[i + 1] - kms[i] <= 30.5 for i in range(len(kms) - 1))
    assert len(pts) <= 5


def test_detour_vertex_survives_thinning():
    # long detour: ~200 km each leg → many subs, must thin to MAX_SAMPLES
    legs = [[19.0, 72.0], [19.8, 72.4], [20.2, 71.9]]
    pts = _sample_points(legs)
    assert len(pts) <= 5
    verts = [p for p in pts if p["vertex"]]
    assert len(verts) == 3                              # start/waypoint/end kept
    assert any(abs(v["lat"] - 19.8) < 0.01 for v in verts)  # THE real detour point
    assert [p["sail_km"] for p in pts] == sorted(p["sail_km"] for p in pts)


# ── point state (threshold mirror of advisory.py) ───────────────────

def test_unknown_when_no_forecast():
    state, row = _point_state(None)
    assert state == "unknown" and "failed" in row["note"]


def test_good_carries_real_numbers():
    state, row = _point_state(_pf())
    assert state == "good"
    assert row["wave_m"] == 1.0 and row["sst_c"] == 29.0 and row["current_kn"] == 0.6


def test_caution_from_48h_wave_even_if_now_calm():
    state, row = _point_state(_pf(wave=1.2, wave48=WAVE_CAUTION_M + 0.1))
    assert state == "caution" and "waves" in row["why"]


def test_danger_from_now_wave_and_gale_gust():
    s1, _ = _point_state(_pf(wave=WAVE_DANGER_M + 0.3))
    s2, row = _point_state(_pf(gust48=GUST_DANGER_KN + 2))
    assert s1 == "danger" and s2 == "danger"
    assert "gale" in row["why"]


def test_strong_current_attaches_honest_note_not_state():
    state, row = _point_state(_pf(current=3.4))
    assert state == "good" and "current" in row["note"]


# ── verdict reduction ───────────────────────────────────────────────

def test_reduce_matrix():
    assert _reduce_verdict(["good", "good", "good"], True)["level"] == "go"
    assert _reduce_verdict(["good", "caution"], True)["level"] == "caution"
    assert _reduce_verdict(["good", "danger", "good"], True)["level"] == "nogo"
    # a failed point is a reason for caution, never silently 'go'
    assert _reduce_verdict(["good", "unknown"], True)["level"] == "caution"
    assert _reduce_verdict(["unknown", "unknown"], None)["level"] == "unknown"
    # land blocked beats everything
    assert _reduce_verdict(["good", "good"], False)["level"] == "nogo"


def test_reduce_counts_known_points():
    v = _reduce_verdict(["good", "unknown", "caution"], True)
    assert v["points_known"] == 2 and v["points_total"] == 3
    assert v["land_verified"] is True
