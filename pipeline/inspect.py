"""`python -m pipeline.inspect` — peek inside a NetCDF / HDF5 file.

Usage:
    # Just show the structure
    python -m pipeline.inspect file.nc

    # Extract a value at a specific lat/lon
    python -m pipeline.inspect file.nc --at 19.0 72.8

    # Use the right variable name (auto-detected for chlorophyll/wind/upwelling)
    python -m pipeline.inspect file.nc --at 19.0 72.8 --var chlor_a

    # Or let it auto-detect based on the file's variables
    python -m pipeline.inspect file.nc --at 19.0 72.8 --auto

The --auto mode uses the new domain extractors (extract_chlorophyll,
extract_wind, extract_upwelling) which handle 0-360 longitude, fill
values, and other MOSDAC-specific quirks.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline import parser
from pipeline.extractors import (
    extract_chlorophyll,
    extract_upwelling,
    extract_wind,
)


def _format_value(pf, variable, lat, lon, debug=False):
    """Try the appropriate domain extractor based on what's in the file."""
    # Detect which kind of data this file is
    has_chlor = any("chlor" in v.lower() for v in pf.variables)
    has_wind = "U" in pf.variables and "V" in pf.variables
    has_upwelling = any("upwelling" in v.lower() for v in pf.variables)

    results = []
    if has_chlor:
        r = extract_chlorophyll(pf, lat, lon, debug=debug)
        if r is not None and "error" not in r:
            results.append(("Chlorophyll-a", r))
    if has_wind:
        r = extract_wind(pf, lat, lon)
        if r is not None and "error" not in r:
            results.append(("Wind vector", r))
    if has_upwelling:
        r = extract_upwelling(pf, lat, lon)
        if r is not None and "error" not in r:
            results.append(("Upwelling index", r))
    return results


def _print_extracted(results, lat, lon):
    if not results:
        print(f"   ❌ No extractable values near ({lat}, {lon})")
        print(f"      (likely land or out of grid)")
        return
    for label, r in results:
        print(f"   🌊 {label}:")
        for k, v in r.items():
            if k == "source":
                print(f"      {k:>14}: {v}")
            elif k == "value":
                flag = ""
                if r.get("valid") is False:
                    flag = "  ⚠ below detection threshold"
                print(f"      {k:>14}: {v:>12.4g} {r.get('units', '')}{flag}")
            elif k in ("u", "v", "speed", "direction_deg", "tau_x", "tau_y", "curl", "samples"):
                print(f"      {k:>14}: {v:>12.4g}")
            elif k == "log":
                if v is not None:
                    print(f"      {k:>14}: {v:>12.4f}  (log10 for plotting)")
                else:
                    print(f"      {k:>14}: (undefined, value ≤ 0)")
            elif k == "interpretation":
                print(f"      {k:>14}: {v}")
            elif k == "valid":
                continue  # already shown as flag
            else:
                print(f"      {k:>14}: {v}")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Inspect a NetCDF / HDF5 satellite data file.",
    )
    p.add_argument("path", help="Path to the .nc or .h5 file")
    p.add_argument(
        "--at",
        nargs=2,
        type=float,
        metavar=("LAT", "LON"),
        help="Extract value at this lat/lon",
    )
    p.add_argument(
        "--var",
        help="Specific variable to extract (default: auto-detect)",
    )
    p.add_argument(
        "--auto",
        action="store_true",
        default=True,
        help="Use the domain extractor (chlorophyll/wind/upwelling)",
    )
    p.add_argument(
        "--no-auto",
        dest="auto",
        action="store_false",
        help="Use the generic parser.extract_at_location instead",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Show raw values even if they look invalid (NaN, negative, huge)",
    )
    args = p.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"❌ File not found: {path}", file=sys.stderr)
        sys.exit(1)

    pf = parser.parse(path)

    # Print summary
    print(f"📁 {path.name}  ({path.stat().st_size / 1024 / 1024:.2f} MB)")
    print()
    print(f"   Type:          {pf.file_type}")
    if pf.satellite:
        print(f"   Satellite:     {pf.satellite}")
    if pf.instrument:
        print(f"   Instrument:    {pf.instrument}")
    if pf.processing_level:
        print(f"   Level:         {pf.processing_level}")
    if pf.product_name:
        print(f"   Product:       {pf.product_name}")
    if pf.date:
        print(f"   Date:          {pf.date.isoformat()}")
    if pf.resolution_km:
        print(f"   Resolution:    {pf.resolution_km} km")
    if pf.version:
        print(f"   Version:       {pf.version}")
    print()

    if pf.warnings:
        print("⚠️  Warnings:")
        for w in pf.warnings:
            print(f"   - {w}")
        print()

    if pf.coordinates:
        print("🌐 Coordinates:")
        for name, arr in pf.coordinates.items():
            if name in ("lat", "latitude"):
                try:
                    print(f"   {name}: {len(arr)} values, "
                          f"min={arr.min():.4f}, max={arr.max():.4f}")
                except Exception:  # noqa: BLE001
                    print(f"   {name}: {arr}")
            elif name in ("lon", "longitude"):
                try:
                    print(f"   {name}: {len(arr)} values, "
                          f"min={arr.min():.4f}, max={arr.max():.4f}")
                except Exception:  # noqa: BLE001
                    print(f"   {name}: {arr}")
            elif name in ("time", "Time"):
                if isinstance(arr, list):
                    print(f"   {name}: {arr}")
                else:
                    print(f"   {name}: {arr}")
        print()

    if pf.variables:
        print(f"📊 Variables ({len(pf.variables)}):")
        for name, info in pf.variables.items():
            print(f"   • {name}")
            print(f"       shape: {'x'.join(str(s) for s in info['shape'])}"
                  f"   dtype: {info['dtype']}   dims: {info['dims']}")
            if "units" in info:
                print(f"       units: {info['units']}")
            if "long_name" in info:
                print(f"       desc:  {info['long_name']}")
            if "sample" in info and isinstance(info["sample"], dict):
                s = info["sample"]
                print(f"       range: "
                      f"min={s.get('min', 0):.4g}, max={s.get('max', 0):.4g}, "
                      f"mean={s.get('mean', 0):.4g}")
        print()

    if pf.file_attrs:
        print("📝 File attributes:")
        for k, v in list(pf.file_attrs.items())[:8]:
            v_short = v[:80] + "..." if len(v) > 80 else v
            print(f"   {k}: {v_short}")
        if len(pf.file_attrs) > 8:
            print(f"   ... ({len(pf.file_attrs) - 8} more)")
        print()

    # Extract at location if requested
    if args.at:
        lat, lon = args.at
        print(f"📍 Extracting at ({lat}, {lon}):")
        if args.auto:
            results = _format_value(pf, args.var, lat, lon, debug=args.debug)
            _print_extracted(results, lat, lon)
        else:
            r = parser.extract_at_location(pf, lat, lon, variable=args.var)
            if r:
                print(f"   Variable: {r.get('variable')}")
                print(f"   Value:    {r.get('value')} {r.get('units', '')}")
                print(f"   At grid:  ({r.get('lat')}, {r.get('lon')})")
                print(f"   Distance: {r.get('distance_deg'):.3f}°")
                print(f"   Source:   {r.get('source')}")
            else:
                print(f"   ❌ No value found near ({lat}, {lon})")


if __name__ == "__main__":
    main()
