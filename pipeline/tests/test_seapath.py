"""SEAPATH engine tests — the round-the-peninsula router.

Mostly pure (synthetic grids, injected verify callbacks) so the honesty
guards are pinned EXACTLY; one real-GLOBE integration test rides the
bundled dataset to prove a subcontinent-class reroute end-to-end.
"""
from __future__ import annotations

import numpy as np

from pipeline import seapath as sp


# ── pure grid tests ─────────────────────────────────────────────────

def test_nearest_water_spirals_out_of_land():
    ocean = np.ones((9, 9), dtype=bool)
    ocean[3:6, 3:6] = False  # 3×3 land blob, (4,4) at its centre
    hit = sp._nearest_water(ocean, (4, 4))
    assert hit is not None and bool(ocean[hit])  # numpy True_, not builtin True
    assert max(abs(hit[0] - 4), abs(hit[1] - 4)) == 2  # first ring outside the blob


def test_dilate_grows_land_one_cell_every_side():
    land = np.zeros((7, 7), dtype=bool)
    land[3, 3] = True
    out = sp._dilate(land, 1)
    assert out[3, 3] and out[2, 3] and out[4, 3] and out[3, 2] and out[3, 4]
    assert out[2, 2]      # square dilation: diagonals grow too (9-cell block)
    assert out.sum() == 9


def test_astar_routes_around_wall_through_gap():
    """A 19×19 ocean with a full-width wall except one gap: the path must
    exist and MUST pass through the gap column cell."""
    ocean = np.ones((19, 19), dtype=bool)
    ocean[:, 9] = False
    ocean[15, 9] = True  # the only gap
    path, pops = sp._astar(ocean, (9, 2), (9, 16), 0.0, 0.0, 1.0, sp.MAX_ASTAR_POPS)
    assert path is not None and pops > 0
    assert (15, 9) in path  # routed through the real gap, not through the wall
    for (i, j) in path:
        assert ocean[i, j]


def test_greedy_legs_takes_longest_verified_hop():
    """verify allows hops of ≤2 dense-steps → legs land exactly on the
    farthest verifiable points each time (0,2,4,5)."""
    dense = [(0.0, float(i)) for i in range(6)]
    verify = lambda a1, a2, b1, b2: abs(b2 - a2) <= 2
    legs = sp._greedy_verified_legs(dense, verify)
    assert legs == [(0.0, 0.0), (0.0, 2.0), (0.0, 4.0), (0.0, 5.0)]


def test_greedy_legs_honest_none_when_adjacent_unverified():
    """If even the NEXT dense point can't be proven water, return None —
    never silently skip a leg (the 'no fake safe line' contract)."""
    dense = [(0.0, float(i)) for i in range(5)]
    verify = lambda a1, a2, b1, b2: b2 <= 0.0  # nothing beyond point 0 verifies
    assert sp._greedy_verified_legs(dense, verify) is None


def test_reroute_refuses_land_destination(monkeypatch):
    """Endpoint legality: a sea path can only connect water to water.
    Destination INSIDE the mask's land → None, before any grid work
    (regression: the old sampler missed exact endpoints at 2 km steps)."""
    class LandDestGlg:
        @staticmethod
        def is_land(lat, lon):
            # only the exact destination point is land
            return np.isclose(np.asarray(lat, dtype=float), 19.05)

    monkeypatch.setattr(sp, "_mask_module", lambda: LandDestGlg)
    assert sp.reroute(19.05, 72.2, 19.05, 72.95) is None


# ── real-data integration (bundled GLOBE, offline) ──────────────────

def test_subcontinent_reroute_around_peninsula_real_mask():
    """THE user case: Bay of Bengal → Mumbai. The straight line cuts
    right across India; the engine must hand back a GLOBE-verified sea
    path around the peninsula — and it must be longer-but-real."""
    import pytest
    pytest.importorskip("global_land_mask")
    from pipeline.routecheck import compute_sea_route, _seg_land_hit

    r = compute_sea_route(15.9225, 83.2170, 19.1441, 72.2917)
    assert r["ok"] is True and r.get("rerouted") is True
    assert len(r["legs"]) >= 4                      # real multi-leg rounding
    assert r["distance_nm"] > r["straight_distance_nm"]  # honest: detour costs
    # rounds the peninsula region (waypoints south of 10.5°N)
    assert min(pt[0] for pt in r["legs"]) < 10.5
    # EVERY returned leg independently verified at native 1 km
    for a, b in zip(r["legs"], r["legs"][1:]):
        assert _seg_land_hit(a[0], a[1], b[0], b[1]) is None, f"unverified leg {a}->{b}"


def test_route_advisory_follows_the_reroute():
    """The advisory must sample ALONG the rerouted path (vertices are
    always kept) — its point budget grows past the 5-point direct cap."""
    import pytest
    pytest.importorskip("global_land_mask")
    from pipeline.routeadvisory import _sample_points

    legs = [[15.9225, 83.217], [9.4025, 79.5317], [9.0025, 79.2117],
            [7.9625, 77.3717], [9.0825, 76.2517], [16.8425, 73.1317],
            [19.1441, 72.2917]]
    direct = _sample_points(legs, max_n=5)
    long_route = _sample_points(legs, max_n=min(16, 2 * len(legs)))
    assert len(long_route) > len(direct)
    verts = [p for p in long_route if p["vertex"]]
    assert len(verts) == len(legs)  # every waypoint kept as evidence
