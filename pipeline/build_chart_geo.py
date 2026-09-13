"""Build frontend/vendor/chart.geojson — the offline nautical-chart basemap.

When neither the user's browser nor the sandbox can reach tile servers
(Arena's preview iframe blocks cross-origin requests; the sandbox itself
currently has zero egress), the map's basemap chain falls forward to the
first-party proxy, which serves locally-drawn graticule tiles. Graticule
alone looks like an abstract grid — "data floating anywhere", not a map
anchored to real geography. This script adds the missing geography:

  * land polygons + coastline  — Natural Earth 1:10m land (via the
    `world-atlas` npm bundle, which vendors the TopoJSON files), so the
    Gujarat/Kutch coastline, Gulf of Kachchh and Saurashtra peninsula
    render at full fidelity.
  * country borders            — Natural Earth 1:50m countries, dashed.

Source of the bundled files:
    npm pack world-atlas@2   →  package/land-10m.json, countries-50m.json
Natural Earth data is public domain (naturalearthdata.com); world-atlas
packages it under BSD-3 (see LICENSE in the tarball).

Output: one FeatureCollection; feature.properties.kind is "land" or
"border", which the frontend styles differently. Clipped to the
India/Arabian-Sea region (ring-level bbox test — rings that intersect
the region are kept whole, so geometry stays valid).

Usage:  python3 pipeline/build_chart_geo.py [world-atlas-package-dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REGION = (45.0, -6.0, 100.0, 41.0)   # lon_min, lat_min, lon_max, lat_max


def _decode_topojson(topo: dict) -> list[list[list[float]]]:
    """TopoJSON arcs (delta-encoded, quantised) -> absolute [lon,lat] arcs."""
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs: list[list[list[float]]] = []
    for arc in topo["arcs"]:
        x = y = 0.0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append([x * sx + tx, y * sy + ty])
        arcs.append(pts)
    return arcs


def _ring_from_arcs(arc_idx: list[int], arcs: list[list[list[float]]]) -> list[list[float]]:
    """Stitch a TopoJSON ring (arc indices; negative = reversed ~i)."""
    ring: list[list[float]] = []
    for i in arc_idx:
        pts = arcs[i] if i >= 0 else list(reversed(arcs[~i]))
        if ring and ring[-1] == pts[0]:
            ring.extend(pts[1:])
        else:
            ring.extend(pts)
    if ring and ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    return ring


def _bbox(ring: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _intersects(b: tuple[float, float, float, float]) -> bool:
    return not (b[2] < REGION[0] or b[0] > REGION[2] or
                b[3] < REGION[1] or b[1] > REGION[3])


# full-fidelity zone — the Kutch / Saurashtra coast the map centres on
CORE = (66.0, 18.0, 74.5, 25.5)


def _simplify(ring: list[list[float]], tol: float) -> list[list[float]]:
    """Iterative Douglas-Peucker. tol in degrees (~0.001° ≈ 110 m)."""
    if len(ring) < 8 or tol <= 0:
        return ring
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        x0, y0 = ring[i0]
        x1, y1 = ring[i1]
        dx, dy = x1 - x0, y1 - y0
        seg = (dx * dx + dy * dy) ** 0.5
        dmax, imax = -1.0, -1
        for i in range(i0 + 1, i1):
            px, py = ring[i]
            if seg < 1e-12:
                d = ((px - x0) ** 2 + (py - y0) ** 2) ** 0.5
            else:
                d = abs(dx * (y0 - py) - dy * (x0 - px)) / seg
            if d > dmax:
                dmax, imax = d, i
        if dmax > tol:
            keep[imax] = True
            stack.append((i0, imax))
            stack.append((imax, i1))
    return [p for p, k in zip(ring, keep) if k]




def _round(ring: list[list[float]], dp: int) -> list[list[float]]:
    """Round coords — 3 dp ≈ 110 m, far below the simplification tolerance;
    JSON strings shrink dramatically (71.234567 -> 71.235)."""
    return [[round(p[0], dp), round(p[1], dp)] for p in ring]


def _tolerance(ring: list[list[float]]) -> float:
    """Full detail on the Kutch coast, coarse for far-away context rings."""
    if _intersects(_bbox(ring)) and _intersects(tuple(CORE)):
        b = _bbox(ring)
        # ring tiny enough to sit inside the core → keep it detailed
        if b[0] >= CORE[0] and b[1] >= CORE[1] and b[2] <= CORE[2] and b[3] <= CORE[3]:
            return 0.0008
        return 0.003
    return 0.02


def _in_core(p: list[float], pad: float = 1.5) -> bool:
    return (CORE[0] - pad <= p[0] <= CORE[2] + pad and
            CORE[1] - pad <= p[1] <= CORE[3] + pad)


def _clip_runs(ring: list[list[float]]) -> list[list[list[float]]]:
    """Cut a (closed) ring into open runs of points near the core, keeping
    one margin point on each side so lines reach slightly past the edge."""
    runs: list[list[list[float]]] = []
    cur: list[list[float]] = []
    n = len(ring) - 1          # last point == first (closed) → skip dupe
    for i in range(n):
        p = ring[i]
        if _in_core(p):
            if not cur:
                cur.append(ring[i - 1])     # margin point before the run
            cur.append(p)
        elif cur:
            cur.append(p)                   # margin point after the run
            runs.append(cur)
            cur = []
    if len(cur) >= 4:
        runs.append(cur)
    return runs


def _rings(geom: dict, arcs: list) -> list[list[list[float]]]:
    """All outer+inner rings of a Polygon/MultiPolygon geometry."""
    gtype = geom.get("type")
    polys: list = []
    if gtype == "Polygon":
        polys = [geom["arcs"]]
    elif gtype == "MultiPolygon":
        polys = geom["arcs"]
    elif gtype == "GeometryCollection":
        out = []
        for g in geom.get("geometries", []):
            out.extend(_rings(g, arcs))
        return out
    else:
        return []
    rings = []
    for poly in polys:
        for arc_idx in poly:
            rings.append(_ring_from_arcs(arc_idx, arcs))
    return rings


def build(atlas_dir: Path) -> dict:
    features: list[dict] = []

    # ── tier 1: context landmass — 1:50m, filled, coarsely simplified ──
    land50 = json.loads((atlas_dir / "land-50m.json").read_text())
    a50 = _decode_topojson(land50)
    n_ctx = 0
    for obj in land50["objects"]["land"]["geometries"]:
        for ring in _rings(obj, a50):
            if _intersects(_bbox(ring)):
                ring = _round(_simplify(ring, 0.02), 3)
                features.append({"type": "Feature",
                                 "properties": {"kind": "land"},
                                 "geometry": {"type": "Polygon",
                                              "coordinates": [ring]}})
                n_ctx += 1

    # ── tier 2: Kutch coast — 1:10m runs inside CORE, stroke-only ──
    # Small rings wholly inside the core stay closed (islands keep their
    # fill); the Eurasia mainland ring is cut into open coastline runs.
    land_topo = json.loads((atlas_dir / "land-10m.json").read_text())
    land_arcs = _decode_topojson(land_topo)
    n_core = 0
    for obj in land_topo["objects"]["land"]["geometries"]:
        for ring in _rings(obj, land_arcs):
            b = _bbox(ring)
            if not _intersects(b):
                continue
            if b[0] >= CORE[0] and b[1] >= CORE[1] and b[2] <= CORE[2] and b[3] <= CORE[3]:
                ring = _round(_simplify(ring, 0.0008), 4)
                features.append({"type": "Feature",
                                 "properties": {"kind": "coast"},
                                 "geometry": {"type": "Polygon",
                                              "coordinates": [ring]}})
                n_core += 1
            else:
                for run in _clip_runs(ring):
                    run = _round(_simplify(run, 0.0012), 4)
                    if len(run) >= 4:
                        features.append({"type": "Feature",
                                         "properties": {"kind": "coast"},
                                         "geometry": {"type": "LineString",
                                                      "coordinates": run}})
                        n_core += 1

    # ── country borders (1:50m) — polygon outlines stroked, not filled ──
    c_topo = json.loads((atlas_dir / "countries-50m.json").read_text())
    c_arcs = _decode_topojson(c_topo)
    n_bord = 0
    for country in c_topo["objects"]["countries"]["geometries"]:
        name = (country.get("properties") or {}).get("name", "?")
        for ring in _rings(country, c_arcs):
            if _intersects(_bbox(ring)):
                ring = _round(_simplify(ring, 0.015), 3)
                features.append({"type": "Feature",
                                 "properties": {"kind": "border", "name": name},
                                 "geometry": {"type": "LineString",
                                              "coordinates": ring}})
                n_bord += 1

    print(f"[chart-geo] context land: {n_ctx}  core coast: {n_core}  "
          f"border rings: {n_bord}")
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    atlas = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watlas/package")
    if not (atlas / "land-10m.json").exists():
        sys.exit(f"world-atlas bundle not found in {atlas} — run: npm pack world-atlas@2")
    geo = build(atlas)
    out = ROOT / "frontend" / "vendor" / "chart.geojson"
    out.write_text(json.dumps(geo, separators=(",", ":")))
    print(f"[chart-geo] wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
