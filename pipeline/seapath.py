"""Ocean pathfinding: when BOTH the straight course and the local detour
budget lose to land, compute a sea-only path AROUND the obstruction —
the way a real skipper would round Sri Lanka going Bay of Bengal →
Mumbai instead of being told "blocked, good luck".

Philosophy (same as the rest of ORCA): NOT an ML guess and NOT a
server lookup. A* — the same shortest-path family Google Maps uses for
roads — runs over the REAL GLOBE 1 km land mask. Then every simplified
leg is PROVEN at full native resolution before we show it. If no water
path verifies inside the search budget we say so plainly rather than
drawing a safe-looking line over a shoal.

Pipeline per attempt:
  1. pool the native mask into coarse cells (0.08° ≈ 8.8 km), probing
     3×3 native points per cell so a thin peninsula can't sneak through
  2. inflate land by 1 cell (~9 km) — keep the coarse path a clean
     corridor off every coastline
  3. A* from start-cell to dest-cell over water cells only
  4. insert elbow cells where diagonal steps would clip corners
  5. greedy simplification: take the LONGEST next hop that full-
     resolution mask sampling proves water-only; repeat — the result
     is a handful of real waypoints, not a staircase of cells
Retries widen the search box (islands → peninsula → the 10°-plus swing
needed to round a subcontinent).

Public API: reroute(from_lat, from_lon, to_lat, to_lon) -> dict | None
"""
from __future__ import annotations

import heapq
import math
from typing import Any, Callable

import numpy as np

# ── tunables (documented in method string of every result) ──────────
CELL_DEG = 0.08                    # ~8.8 km pooled cells
PAD_LADDER_DEG = (1.5, 4.0, 8.0, 12.0)  # search windows, widening
DILATE_CHOICES = (1, 2)            # cells of coast keep-off (× ~8.8 km)
SUB = 3                            # 3×3 native probes per pooled cell
MAX_ASTAR_POPS = 2_500_000         # safety brake, not a target
EARTH_R_KM = 6371.0
DEG_KM = 111.32                    # cheap metric for A* costs (equirect)

Point = tuple[float, float]        # (lat, lon)
Cell = tuple[int, int]             # (row, col) in pooled grid


# ── loading the REAL mask (vectorized lookups) ──────────────────────
def _mask_module():
    """The global_land_mask module object holding the native array, or
    None when the optional dependency is absent (callers then say
    'unable', never invent)."""
    try:
        import global_land_mask.globe as glg
        _ = glg.is_land(0.0, 0.0)  # sanity: array present + indexed
        return glg
    except Exception:  # noqa: BLE001
        return None


def _probe_pooled(glg, minlat: float, maxlat: float,
                  minlon: float, maxlon: float,
                  cell_deg: float, sub: int) -> tuple[np.ndarray, float, float]:
    """Pooled land mask for the bbox.

    Every coarse cell is probed at sub×sub native-resolution points and
    counts as LAND if ANY probe hits land. Returns (land_grid, minlat_used,
    minlon_used) — the last two after integer trimming so cell (0,0) maps
    to a known origin.
    """
    step = cell_deg / sub
    lats = np.arange(minlat + step / 2, maxlat, step)
    lons = np.arange(minlon + step / 2, maxlon, step)
    if len(lats) < sub or len(lons) < sub:
        raise ValueError("bbox smaller than one cell")
    LAT, LON = np.meshgrid(lats, lons, indexing="ij")
    land_probe = np.asarray(glg.is_land(LAT, LON), dtype=bool)
    r = (len(lats) // sub) * sub
    c = (len(lons) // sub) * sub
    land = land_probe[:r, :c].reshape(r // sub, sub, c // sub, sub).any(axis=(1, 3))
    return land, float(minlat), float(minlon)


def _dilate(land: np.ndarray, n: int) -> np.ndarray:
    """Grow land cells by n in every direction (cheap max-pool via rolls;
    edge wrap is harmless — poles are outside every sane bbox)."""
    out = land.copy()
    for di in range(-n, n + 1):
        for dj in range(-n, n + 1):
            if di or dj:
                out |= np.roll(np.roll(land, di, axis=0), dj, axis=1)
    return out


# ── geometry helpers on the pooled grid ─────────────────────────────
def _lat_of(i: float, minlat: float, cell_deg: float) -> float:
    return minlat + (i + 0.5) * cell_deg


def _lon_of(j: float, minlon: float, cell_deg: float) -> float:
    return minlon + (j + 0.5) * cell_deg


def _equirect_km(a: Cell, b: Cell, minlat: float, minlon: float, cell_deg: float,
                 coslat_row: np.ndarray) -> float:
    """Fast consistent metric for A* edges/heuristic (final distances are
    recomputed with exact haversine afterwards)."""
    la1 = math.radians(_lat_of(a[0], minlat, cell_deg))
    la2 = math.radians(_lat_of(b[0], minlat, cell_deg))
    dlat = la2 - la1
    dlon = math.radians((b[1] - a[1]) * cell_deg)
    mid = (la1 + la2) / 2
    return EARTH_R_KM * math.sqrt(dlat * dlat + (dlon * math.cos(mid)) ** 2)


def _cell_of(lat: float, lon: float, minlat: float, minlon: float,
             cell_deg: float, rows: int, cols: int) -> Cell:
    i = int((lat - minlat) / cell_deg)
    j = int((lon - minlon) / cell_deg)
    return min(max(i, 0), rows - 1), min(max(j, 0), cols - 1)


def _nearest_water(ocean: np.ndarray, start: Cell, max_ring: int = 48) -> Cell | None:
    """Spiral out from a cell until a water cell shows (start/dest may sit
    inside a cell that pooling counts as land because a sliver of coast
    shares it)."""
    i0, j0 = start
    rows, cols = ocean.shape
    if ocean[i0, j0]:
        return start
    for r in range(1, max_ring + 1):
        best: Cell | None = None
        best_d = 1e18
        for di in range(-r, r + 1):
            for dj in (-r, r):
                i, j = i0 + di, j0 + dj
                if 0 <= i < rows and 0 <= j < cols and ocean[i, j]:
                    d = abs(di) + abs(dj)
                    if d < best_d:
                        best, best_d = (i, j), d
        for dj in range(-r + 1, r):
            for di in (-r, r):
                i, j = i0 + di, j0 + dj
                if 0 <= i < rows and 0 <= j < cols and ocean[i, j]:
                    d = abs(di) + abs(dj)
                    if d < best_d:
                        best, best_d = (i, j), d
        if best is not None:
            return best
    return None


_DIRS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def _astar(ocean: np.ndarray, s: Cell, g: Cell, minlat: float, minlon: float,
           cell_deg: float, max_pops: int) -> tuple[list[Cell] | None, int]:
    """Classic A* over water cells (8-neighbour). Returns (path, pops)."""
    rows, cols = ocean.shape
    coslat_row = np.cos(np.radians(_lat_of(np.arange(rows), minlat, cell_deg)))
    coslat_row = np.clip(coslat_row, 0.01, 1.0)

    def h(c: Cell) -> float:
        return _equirect_km(c, g, minlat, minlon, cell_deg, coslat_row)

    gs: dict[Cell, float] = {s: 0.0}
    came: dict[Cell, Cell] = {}
    closed: set[Cell] = set()
    pq: list[tuple[float, int, Cell]] = [(h(s), 0, s)]
    tick = 0
    pops = 0
    while pq and pops < max_pops:
        _, _, c = heapq.heappop(pq)
        if c in closed:
            continue
        closed.add(c)
        pops += 1
        if c == g:
            path = [c]
            while c in came:
                c = came[c]
                path.append(c)
            path.reverse()
            return path, pops
        ci, cj = c
        base_g = gs[c]
        for di, dj in _DIRS:
            ni, nj = ci + di, cj + dj
            if not (0 <= ni < rows and 0 <= nj < cols):
                continue
            if not ocean[ni, nj]:
                continue
            n = (ni, nj)
            if n in closed:
                continue
            ng = base_g + _equirect_km(c, n, minlat, minlon, cell_deg, coslat_row)
            if ng < gs.get(n, math.inf):
                gs[n] = ng
                came[n] = c
                tick += 1
                heapq.heappush(pq, (ng + h(n), tick, n))
    return None, pops


def _centers_with_elbows(path: list[Cell], ocean: np.ndarray,
                         minlat: float, minlon: float,
                         cell_deg: float) -> list[Point]:
    """Cell-centre path + elbow cells wherever a diagonal step would clip
    a land corner (the extra corner cell that is water-side)."""
    pts: list[Point] = []
    for k, cell in enumerate(path):
        pts.append((_lat_of(cell[0], minlat, cell_deg),
                    _lon_of(cell[1], minlon, cell_deg)))
        if k + 1 < len(path):
            nxt = path[k + 1]
            if cell[0] != nxt[0] and cell[1] != nxt[1]:
                e1 = (cell[0], nxt[1])
                e2 = (nxt[0], cell[1])
                for e in (e1, e2):
                    if ocean[e[0], e[1]]:
                        pts.insert(len(pts) - 1 + 1, (  # append after current
                            _lat_of(e[0], minlat, cell_deg),
                            _lon_of(e[1], minlon, cell_deg)))
                        break
    return pts


def _greedy_verified_legs(dense: list[Point],
                          verify: Callable[[float, float, float, float], bool]
                          ) -> list[Point] | None:
    """Waypoint simplification with PROOF at every hop: from the current
    point, the farthest dense point reachable through water (native-
    resolution sampling) becomes the next waypoint. Exponential growth +
    binary refine keeps native checks logarithmic per hop. Returns None
    when even an adjacent pair fails (never silently skips it)."""
    n = len(dense)
    legs = [dense[0]]
    i = 0
    while i < n - 1:
        if verify(dense[i][0], dense[i][1], dense[n - 1][0], dense[n - 1][1]):
            legs.append(dense[n - 1])
            i = n - 1
            break
        last = i            # NOTHING beyond i is trusted until verify says so
        span = 1
        done = False
        while not done:
            j = min(n - 1, i + span)
            if verify(dense[i][0], dense[i][1], dense[j][0], dense[j][1]):
                last = j
                span *= 2
                if j == n - 1:
                    done = True
            else:
                lo, hi = last, j
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    if verify(dense[i][0], dense[i][1], dense[mid][0], dense[mid][1]):
                        lo = mid
                    else:
                        hi = mid
                last = lo
                done = True
        if last == i:
            return None
        legs.append(dense[last])
        i = last
    return legs


def _hav_km(a: Point, b: Point) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    s = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(s))


# ── public entry ────────────────────────────────────────────────────
def reroute(from_lat: float, from_lon: float,
            to_lat: float, to_lon: float,
            verify: Callable[[float, float, float, float], bool] | None = None,
            ) -> dict[str, Any] | None:
    """Find a water-only path start → dest on the GLOBE mask.

    verify(a_lat, a_lon, b_lat, b_lon) = True when the segment is water
    end-to-end at NATIVE mask resolution (default: routecheck's sampler,
    the exact same legality proof the straight course uses). Returns
    None when the mask is unavailable or no path verifies in budget —
    callers then report the honest 'no route' state.
    """
    glg = _mask_module()
    if glg is None:
        return None
    # Endpoint legality: a sea path can only connect WATER to WATER —
    # never pretend we found one INTO land. (Regression guard: a route
    # ending on the GLOBE-land cell at 72.95°E once "passed" because the
    # 2 km leg sampler doesn't include the exact endpoint — so the
    # endpoint itself must be probed explicitly before gridding.)
    try:
        if bool(glg.is_land(float(to_lat), float(to_lon))):
            return None
        if bool(glg.is_land(float(from_lat), float(from_lon))):
            return None
    except Exception:  # noqa: BLE001
        return None
    if verify is None:
        from pipeline.routecheck import _seg_land_hit

        def verify(plat1: float, plon1: float, plat2: float, plon2: float) -> bool:
            try:
                return _seg_land_hit(plat1, plon1, plat2, plon2) is None
            except Exception:  # noqa: BLE001
                return False

    lo_lat, hi_lat = min(from_lat, to_lat), max(from_lat, to_lat)
    lo_lon, hi_lon = min(from_lon, to_lon), max(from_lon, to_lon)

    best: dict[str, Any] | None = None
    for pad in PAD_LADDER_DEG:
        minlat = max(-85.0, lo_lat - pad)
        maxlat = min(85.0, hi_lat + pad)
        minlon = max(-179.9, lo_lon - pad)
        maxlon = min(179.9, hi_lon + pad)
        try:
            land, mla, mlo = _probe_pooled(glg, minlat, maxlat, minlon, maxlon,
                                           CELL_DEG, SUB)
        except Exception:  # noqa: BLE001
            continue
        rows, cols = land.shape
        for dil in DILATE_CHOICES:
            ocean = ~_dilate(land, dil)
            s0 = _cell_of(from_lat, from_lon, mla, mlo, CELL_DEG, rows, cols)
            g0 = _cell_of(to_lat, to_lon, mla, mlo, CELL_DEG, rows, cols)
            s = _nearest_water(ocean, s0)
            g = _nearest_water(ocean, g0)
            if s is None or g is None:
                continue
            try:
                path, pops = _astar(ocean, s, g, mla, mlo, CELL_DEG,
                                    MAX_ASTAR_POPS)
            except Exception:  # noqa: BLE001
                continue
            if not path:
                continue
            dense = _centers_with_elbows(path, ocean, mla, mlo, CELL_DEG)
            dense_pts: list[Point] = [(from_lat, from_lon)] + dense + [(to_lat, to_lon)]
            legs = _greedy_verified_legs(dense_pts, verify)
            if not legs or len(legs) < 2:
                continue
            dist = sum(_hav_km(a, b) for a, b in zip(legs, legs[1:]))
            best = {
                "found": True,
                "legs": [[round(a, 4), round(b, 4)] for a, b in legs],
                "waypoints": [[round(a, 4), round(b, 4)] for a, b in legs[1:-1]],
                "distance_km": round(dist, 1),
                "distance_nm": round(dist / 1.852, 1),
                "astar_pops": pops,
                "grid_cells": rows * cols,
                "cell_deg": CELL_DEG,
                "pad_deg": pad,
                "coast_buffer_cells": dil,
                "method": (f"A* over GLOBE-mask pooled {CELL_DEG}° cells "
                           f"(3×3 native probes/cell, coast inflated {dil} cell, "
                           f"window pad {pad}°); every final leg re-verified at "
                           f"native 1 km — no invented shortcut"),
            }
            return best
    return best
