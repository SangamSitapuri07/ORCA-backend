"""Evidence-grade dump of a MOSDAC product file.

Why this exists (2026-09-13): three datasets were kept disabled with the
verdict "we need the exact official product files/metadata" — but the
inspection tooling we had only looked at the xarray root-group view, so
HDF5 swath files looked like they "lack usable latitude/longitude" and a
product whose *title* attribute says 'OSCAT3_GLO_25km' looked like the
wrong product. This module dumps EVERYTHING — recursive HDF5 groups,
every attribute (scale_factor, add_offset, _FillValue, valid_range…),
decoded value statistics per variable, and a parseability checklist —
so an activation decision is made on evidence, not vibes.

Run:
    python -m pipeline.deepdump file.nc            # human-readable dump
    python -m pipeline.deepdump file.h5 --json     # machine-readable

Used by tools/unblock_mosdac.py to write docs/formats/*.md evidence.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pipeline import parser

# What "wind" can look like, mirroring extractors._U_NAMES etc. so the
# checklist verdict matches what our extractors can actually read.
_GRID_UV_PAIRS = (("u10", "v10"), ("u_wind", "v_wind"), ("u", "v"), ("uwind", "vwind"))
_SPEED_NAMES = ("wind_speed", "windspeed", "wspd", "speed")
_DIR_NAMES = ("wind_dir", "winddir", "wdir", "direction")
_FLAG_HINTS = ("flag", "quality", "qc")
_TIME_HINTS = ("time", "date", "epoch")
_LAT_NAMES = ("lat", "latitude")
_LON_NAMES = ("lon", "longitude")


def _attr_str(v) -> str:
    try:
        if isinstance(v, bytes):
            return v.decode("utf-8", "replace")
        return str(v)
    except Exception:  # noqa: BLE001
        return repr(v)


def _base(name: str) -> str:
    return name.split("/")[-1].lower()


def _decoded_stats(arr, attrs: dict) -> dict[str, Any]:
    """Min/max/mean/%valid after applying packing + fill masking."""
    import numpy as np
    from pipeline.extractors import _decode_swath_array

    try:
        arr = np.asarray(arr)
        if arr.size == 0 or not np.issubdtype(arr.dtype, np.number):
            return {}
        # cap work: stride-read huge arrays
        if arr.size > 4_000_000:
            step = int(arr.size // 2_000_000) + 1
            arr = arr.reshape(-1)[::step].reshape(arr.shape[:-1] + (-1,)) \
                if arr.ndim > 1 else arr[::step]
        dec = _decode_swath_array(arr, attrs)
        valid = np.isfinite(dec)
        if not valid.any():
            return {"valid_pct": 0.0}
        vv = dec[valid]
        return {
            "valid_pct": round(100.0 * valid.sum() / dec.size, 2),
            "min": round(float(vv.min()), 5),
            "max": round(float(vv.max()), 5),
            "mean": round(float(vv.mean()), 5),
        }
    except Exception as exc:  # noqa: BLE001
        return {"stats_error": str(exc)[:120]}


def deep_dump(path: str | Path) -> dict[str, Any]:
    """Full structural + statistical dump of one product file."""
    p = Path(path)
    ev: dict[str, Any] = {
        "file": {
            "name": p.name,
            "size_mb": round(p.stat().st_size / 1024 / 1024, 2),
            "sha256": _sha256(p),
        },
    }

    # 1. filename-level metadata (no I/O)
    meta = parser.parse_filename(p.name)
    ev["filename_parse"] = {k: (str(v) if v is not None else None)
                            for k, v in meta.items() if k != "date"}
    ev["filename_parse"]["date"] = str(meta.get("date") or "")

    # 2. full parse (xarray root view + h5py recursive walk + swath flags)
    pf = parser.parse(p)
    ev["file_type"] = pf.file_type
    ev["swath"] = {
        "is_swath": pf.swath,
        "lat_var": pf.swath_lat,
        "lon_var": pf.swath_lon,
    }
    ev["global_attrs"] = dict(pf.file_attrs)
    ev["warnings"] = list(pf.warnings)

    # 3. per-variable evidence: attrs + decoded stats
    variables = {}
    latlon_2d = []
    for name, info in pf.variables.items():
        entry = {
            "dtype": info.get("dtype"),
            "shape": info.get("shape"),
            "units": info.get("units"),
            "long_name": info.get("long_name"),
            "attrs": info.get("attrs", {}),
        }
        # read + decode if the scientific stack can open this file
        if pf.file_type in ("NetCDF3", "NetCDF4", "HDF5"):
            try:
                values, var_attrs = _read_var(p, pf.file_type, name)
                entry["decoded"] = _decoded_stats(values, var_attrs)
                b = _base(name)
                if len(values.shape) == 2 and (b in _LAT_NAMES or b in _LON_NAMES):
                    latlon_2d.append(name)
            except Exception as exc:  # noqa: BLE001
                entry["read_error"] = str(exc)[:120]
        variables[name] = entry
    ev["variables"] = variables
    ev["latlon_2d_vars"] = latlon_2d

    # 4. grid coordinates (1D), if any
    coords = {}
    for key in ("lat", "lon"):
        arr = pf.coordinates.get(key)
        if arr is not None and len(arr):
            coords[key] = {
                "n": int(len(arr)),
                "min": round(float(arr.min()), 4),
                "max": round(float(arr.max()), 4),
            }
    if pf.coordinates.get("time"):
        coords["time_values"] = pf.coordinates["time"][:3]
    ev["grid_coords"] = coords

    # 5. the verdict checklist — can OUR extractors read this file?
    ev["checklist"] = _checklist(pf, ev)
    return ev


def _read_var(path: Path, file_type: str, name: str):
    """Read one variable (any group depth) → (values, attrs)."""
    import numpy as np
    if file_type == "HDF5" or path.suffix.lower() in (".h5", ".hdf5", ".he5"):
        import h5py
        with h5py.File(path, "r") as f:
            obj = f[name]
            return np.asarray(obj[()]), {k: obj.attrs[k] for k in obj.attrs}
    import xarray as xr
    engine = "netcdf4"
    with xr.open_dataset(path, engine=engine) as ds:
        var = ds[name]
        return var.values, {k: var.attrs[k] for k in var.attrs}


def _checklist(pf, ev: dict) -> dict[str, Any]:
    """Map the file's contents onto what ORCA's extractors need."""
    names = {v.lower(): v for v in pf.variables}
    bases = {_base(v): v for v in pf.variables}
    shapes = {v: (pf.variables[v].get("shape") or []) for v in pf.variables}

    def find2d(cands):
        for c in cands:
            for v in (names.get(c), bases.get(c)):
                if v and len(shapes[v]) == 2:
                    return v
        return None

    lat1d = "lat" in pf.coordinates or "latitude" in pf.coordinates
    lat2d = pf.swath_lat or find2d(_LAT_NAMES)
    lon2d = pf.swath_lon or find2d(_LON_NAMES)
    has_geo = bool(lat1d or (lat2d and lon2d))

    u = find2d(_grid_uv_bases(_GRID_UV_PAIRS)[0])
    v = find2d(_grid_uv_bases(_GRID_UV_PAIRS)[1])
    spd = find2d(_SPEED_NAMES)
    drc = find2d(_DIR_NAMES)
    has_wind = bool((u and v) or (spd and drc))

    flags = [x for x in pf.variables if any(h in _base(x) for h in _FLAG_HINTS)]
    times = [x for x in pf.variables if any(h in _base(x) for h in _TIME_HINTS)]
    has_time = bool(times or pf.coordinates.get("time")
                    or ev.get("filename_parse", {}).get("date"))

    scaled = [x for x, i in pf.variables.items()
              if any(k in (i.get("attrs") or {}) for k in
                     ("scale_factor", "add_offset", "SCALE_FACTOR", "ADD_OFFSET"))]

    if has_wind and has_geo:
        mode = "swath" if (lat2d and lon2d and not lat1d) else "grid"
        verdict = "WIND-PARSE-READY"
    else:
        verdict = "NOT-WIND"
        mode = None
    return {
        "latlon": {"present": has_geo, "mode": ("grid" if lat1d else
                                                "swath-2d" if has_geo else None),
                   "lat_var": (pf.coordinates.get("lat") is not None and "1D coord")
                              or lat2d, "lon_var": lon2d},
        "wind": {"present": has_wind, "u_var": u, "v_var": v,
                 "speed_var": spd, "dir_var": drc},
        "time": {"present": bool(has_time), "time_vars": times[:4]},
        "quality_flags": flags[:6],
        "packed_vars": scaled[:8],
        "verdict": verdict,
        "wind_mode": mode,
    }


def _grid_uv_bases(pairs):
    us, vs = [], []
    for u, v in pairs:
        us.append(u)
        vs.append(v)
    return us, vs


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def render_markdown(ev: dict) -> str:
    """Human/markdown rendering of a deep_dump result."""
    f = ev["file"]
    lines = [
        f"# Product evidence — `{f['name']}`",
        "",
        f"- size: **{f['size_mb']} MB** · sha256[:16]: `{f['sha256']}` · "
        f"type: **{ev['file_type']}** · swath: **{ev['swath']['is_swath']}**",
        f"- filename parse: `{ev['filename_parse']}`",
        "",
        "## Verdict",
        "",
        f"- **{ev['checklist']['verdict']}** (wind mode: {ev['checklist']['wind_mode']})",
        f"- lat/lon: {ev['checklist']['latlon']}",
        f"- wind vars: {ev['checklist']['wind']}",
        f"- time: {ev['checklist']['time']}",
        f"- quality flags: {ev['checklist']['quality_flags'] or 'none found'}",
        f"- packed (scale/offset) vars: {ev['checklist']['packed_vars'] or 'none found'}",
        "",
        "## Global attributes",
        "",
    ]
    for k, v in list(ev["global_attrs"].items())[:25]:
        lines.append(f"- `{k}`: {v}")
    if ev.get("grid_coords"):
        lines += ["", "## Grid coordinates", ""]
        for k, v in ev["grid_coords"].items():
            lines.append(f"- {k}: {v}")
    lines += ["", "## Variables", "",
              "| variable | dtype | shape | units | decoded min/max (valid %) |",
              "|---|---|---|---|---|"]
    for name, info in ev["variables"].items():
        dec = info.get("decoded") or {}
        stat = (f"{dec.get('min')} … {dec.get('max')} ({dec.get('valid_pct')}%)"
                if dec else (info.get("read_error") or "—"))
        lines.append(f"| `{name}` | {info.get('dtype')} | {info.get('shape')} "
                     f"| {info.get('units') or '—'} | {stat} |")
    if ev.get("warnings"):
        lines += ["", "## Warnings", ""]
        lines += [f"- {w}" for w in ev["warnings"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.deepdump file.nc|h5 [--json]")
        sys.exit(1)
    as_json = "--json" in sys.argv
    target = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    ev = deep_dump(target)
    if as_json:
        print(json.dumps(ev, indent=2, default=str))
    else:
        print(render_markdown(ev))
