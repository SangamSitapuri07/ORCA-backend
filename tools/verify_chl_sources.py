"""
Cross-verify ORCA's chlorophyll value against 3 INDEPENDENT sources.

You said another AI told you the chlorophyll is wrong. Let's check.

Queries 3 different satellites for Chennai (13.5, 80.5) on 2026-08-15,
0.2° box (same as ORCA's box), and reports the value each one gives.

Sources:
  1. NOAA VIIRS DINEOF gap-filled (what ORCA currently uses)
  2. ESA OC-CCI v6.0 (gold standard, used by IPCC)
  3. NASA Aqua MODIS (original, non-gap-filled)

Run:
    python verify_chl_sources.py
"""
import sys as _sys, pathlib as _pathlib  # tools/ se bhi repo-root imports kaam karein
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

import json
import sys
import urllib.parse
import urllib.request


# Three independent chlorophyll sources
SOURCES = [
    {
        "name": "NOAA VIIRS DINEOF (gap-filled, what ORCA uses)",
        # NOTE: This dataset's axis order is time, altitude, lat, lon
        # (altitude must be specified, even though it's 0.0 only).
        "url": (
            "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSDINEOFDaily.json"
            "?chlor_a%5B(2026-08-15T12:00:00Z)%5D%5B(0.0):1:(0.0)%5D"
            "%5B(13.4):1:(13.6)%5D%5B(80.4):1:(80.6)%5D"
        ),
        "var": "chlor_a",
        "col_index": 4,  # chlor_a is column 4 in NOAA DINEOF CSV
        "col_lat": 2,
        "col_lon": 3,
    },
    {
        "name": "ESA OC-CCI v6.0 (IPCC standard, 1km, no altitude axis)",
        "url": (
            "https://comet.nefsc.noaa.gov/erddap/griddap/occci_v6_daily_1km.json"
            "?chlor_a%5B(2026-08-15T12:00:00Z)%5D%5B(13.4):1:(13.6)%5D%5B(80.4):1:(80.6)%5D"
        ),
        "var": "chlor_a",
        "col_index": 3,
        "col_lat": 1,
        "col_lon": 2,
    },
    {
        "name": "NASA Aqua MODIS (standard, 4km, 8-day)",
        "url": (
            "https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMH1chla8day.json"
            "?chlorophyll%5B(2026-08-13T12:00:00Z)%5D%5B(13.4):1:(13.6)%5D%5B(80.4):1:(80.6)%5D"
        ),
        "var": "chlorophyll",
        "col_index": 4,
        "col_lat": 2,
        "col_lon": 3,
    },
]


def fetch_chl(source, lat=13.5, lon=80.5):
    """Fetch and pick the cell nearest to (lat, lon)."""
    try:
        req = urllib.request.Request(
            source["url"], headers={"User-Agent": "ORCA-verify/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = data.get("table", {}).get("rows", [])
        if not rows:
            return None, "no data in response"

        # Pick nearest cell
        nearest = None
        nearest_dist = float("inf")
        all_vals = []
        for row in rows:
            v = row[source["col_index"]]
            if v is None:
                continue
            all_vals.append(v)
            try:
                cell_lat = row[source["col_lat"]]
                cell_lon = row[source["col_lon"]]
            except (IndexError, TypeError):
                continue
            import math
            d = math.hypot(cell_lat - lat, cell_lon - lon)
            if d < nearest_dist:
                nearest_dist = d
                nearest = v
        if nearest is None:
            return None, "all values are null"
        return {
            "nearest": nearest,
            "box_min": min(all_vals),
            "box_max": max(all_vals),
            "box_mean": sum(all_vals) / len(all_vals),
            "n": len(all_vals),
            "dist_deg": round(nearest_dist, 3),
        }, None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def main():
    print("=" * 78)
    print("Cross-verify chlorophyll for Chennai (13.5, 80.5) on 2026-08-15")
    print("0.2° box  (13.4-13.6, 80.4-80.6)  — same as ORCA's query")
    print("=" * 78)

    orca_claim = 0.93
    print(f"\n  ORCA OLD value:  {orca_claim} mg/m³  (was box mean of 0.2° box)")
    print(f"  ORCA NEW value:  uses NEAREST CELL instead of box mean")
    print(f"  (Note: ORCA's old value was a BOX MEAN of a 0.2° region.")
    print(f"   Coastal blooms + offshore oligotrophic water can give")
    print(f"   10-100x spread inside the same box. We report BOTH the")
    print(f"   box mean AND the cell nearest the click point.)\n")

    for src in SOURCES:
        print(f"  [{src['name']}]")
        result, err = fetch_chl(src)
        if err:
            print(f"    FAILED: {err}")
        else:
            box_mean_off = abs(result["box_mean"] - orca_claim)
            nearest_off = abs(result["nearest"] - orca_claim)
            print(f"    n={result['n']:3d}  box_min={result['box_min']:.3f}  "
                  f"box_max={result['box_max']:.3f}  box_mean={result['box_mean']:.3f}")
            print(f"    NEAREST CELL = {result['nearest']:.3f} mg/m³  "
                  f"(at {result['dist_deg']:.3f}° from click point)")
            if box_mean_off < 0.15:
                print(f"    ✓ Box mean matches ORCA ({box_mean_off:.2f} off)")
            elif nearest_off < 0.15:
                print(f"    ✓ Nearest cell matches ORCA (box mean was misleading)")
            else:
                ratio = result["nearest"] / orca_claim if orca_claim else 0
                print(f"    ✗ OFF: nearest {result['nearest']:.2f} vs ORCA {orca_claim} ({ratio:.2f}x)")
        print()


if __name__ == "__main__":
    main()
