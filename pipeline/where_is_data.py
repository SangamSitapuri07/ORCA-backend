"""`python -m pipeline.where_is_data <file>` — find where the data actually is.

Useful for diagnosing files where extraction returns NaN: tells you
the global NaN fraction and shows 5 sample ocean points to confirm
the file isn't entirely masked.

Run:
    python -m pipeline.where_is_data file.nc
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from pipeline import parser


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Find where valid data exists in a NetCDF file.",
    )
    p.add_argument("path", help="Path to the .nc or .h5 file")
    args = p.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"❌ File not found: {path}", file=sys.stderr)
        sys.exit(1)

    pf = parser.parse(path)
    print(f"📁 {path.name}  ({path.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"   File type: {pf.file_type}")
    print()

    # Pick the first 2D or 4D variable
    target = None
    for name, info in pf.variables.items():
        if info.get("dtype", "").startswith("float"):
            target = name
            break

    if not target:
        print("❌ No float variables found")
        return

    print(f"Examining variable: {target}")
    print()

    # Open and analyze
    import xarray as xr
    if pf.file_type in ("NetCDF3", "NetCDF4", "HDF5"):
        engine = "netcdf4"
    else:
        engine = "scipy"

    with xr.open_dataset(path, engine=engine) as ds:
        lats = ds.coords.get("lat", ds.coords.get("latitude"))
        lons = ds.coords.get("lon", ds.coords.get("longitude"))
        if lats is None or lons is None:
            print("❌ No lat/lon coords found")
            return

        lats_v = lats.values
        lons_v = lons.values
        print(f"Lat: {len(lats_v)} values, {lats_v[0]:.4f} to {lats_v[-1]:.4f}")
        print(f"     ascending: {lats_v[-1] > lats_v[0]}")
        print(f"Lon: {len(lons_v)} values, {lons_v[0]:.4f} to {lons_v[-1]:.4f}")
        print(f"     ascending: {lons_v[-1] > lons_v[0]}")
        print()

        arr = ds[target].values
        # Collapse 4D to 2D
        if arr.ndim == 4:
            arr = arr[0, 0, :, :]
        elif arr.ndim == 3:
            arr = arr[0, :, :]

        total = arr.size
        # Count valid (non-NaN, not fill) values
        try:
            import numpy as np
            valid_mask = ~np.isnan(arr)
            if hasattr(arr, 'mask'):
                valid_mask = valid_mask & ~arr.mask
            valid = int(valid_mask.sum())
            pct = 100 * valid / total
        except Exception as e:  # noqa: BLE001
            print(f"Could not count valid: {e}")
            valid = -1
            pct = 0

        print(f"Valid cells: {valid:,} / {total:,} ({pct:.1f}%)")
        print(f"Range: min={float(arr[~np.isnan(arr)].min()):.4f}, "
              f"max={float(arr[~np.isnan(arr)].max()):.4f}, "
              f"mean={float(arr[~np.isnan(arr)].mean()):.4f}")
        print()

        # Check a 5x5 grid of well-known ocean points
        # Spread across all oceans to find any valid data
        test_points = [
            ("Indian Ocean (Mumbai)", 19.0, 72.8),
            ("Bay of Bengal", 15.0, 88.0),
            ("Arabian Sea central", 15.0, 65.0),
            ("Equatorial Pacific", 0.0, -150.0),
            ("North Atlantic", 40.0, -30.0),
            ("South China Sea", 15.0, 115.0),
            ("Coral Sea", -18.0, 155.0),
            ("Southern Ocean", -55.0, 0.0),
            ("Mediterranean", 38.0, 15.0),
            ("Caribbean", 18.0, -75.0),
        ]

        print("Sample points (5x5 max-search around each):")
        print(f"{'Location':<25} {'Request':<14} {'Grid (lat,lon)':<22} {'Val':<10} {'NaN count 5x5':<10}")
        print("-" * 100)

        for label, lat_req, lon_req in test_points:
            # Find nearest indices
            lat_idx = int((abs(lats_v - lat_req)).argmin())
            lon_idx = int((abs(lons_v - lon_req)).argmin())
            grid_lat = float(lats_v[lat_idx])
            grid_lon = float(lons_v[lon_idx])

            # 5x5 NaN count
            nan_count = 0
            total_count = 0
            val = float('nan')
            for dlat in range(-5, 6):
                for dlon in range(-5, 6):
                    ni, nj = lat_idx + dlat, lon_idx + dlon
                    if 0 <= ni < arr.shape[0] and 0 <= nj < arr.shape[1]:
                        total_count += 1
                        v = float(arr[ni, nj])
                        if math.isnan(v):
                            nan_count += 1
                        elif val != val:  # NaN check
                            val = v

            val_str = f"{val:.4f}" if not math.isnan(val) else "NaN"
            print(f"{label:<25} ({lat_req},{lon_req})  "
                  f"({grid_lat:.2f},{grid_lon:.2f})   {val_str:<10} {nan_count}/{total_count}")


if __name__ == "__main__":
    main()
