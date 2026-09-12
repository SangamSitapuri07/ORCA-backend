"""Domain extractors for ORCA — turn a ParsedFile into usable values.

Three products are supported:

  * **chlorophyll** — from JPSS2/VIIRS or EOS-06/OCM (variable: `chlor_a`)
  * **wind** — from EOS-06/Scatterometer (variables: U, V, TAUX, TAUY, CURL, ...)
  * **upwelling** — from EOS-06/Scatterometer (variable: `Upwelling_index`)

Each extractor returns a typed dict with proper units. If extraction fails
(e.g., variable missing), it returns None — the caller decides what to do.

All extractors:
  - Handle 4D arrays (time, lev, lat, lon) by collapsing to nearest cell
  - Handle 0-360 longitude (the convention EOS-06 uses)
  - Mask land/fill values using _FILLVALUE / NaN
  - Compute derived quantities (wind speed/direction from U/V)
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


# Standard fill values for ocean data
_FILL_FLOAT = -999.0
# Upwelling file uses a very large negative fill value
_UPWELLING_FILL = -1e6


def _nearest_index(arr: np.ndarray, value: float) -> int:
    """Index of the element in `arr` closest to `value`."""
    return int(np.argmin(np.abs(arr - value)))


def _normalize_lon(lon: float) -> float:
    """Convert longitude to 0-360 range (MOSDAC/EOS-06 convention).

    Examples:
        -180 -> 180
        -90 -> 270
        72.8 -> 72.8
    """
    if lon < 0:
        return lon + 360
    return lon


def _collapse_4d(arr: np.ndarray) -> np.ndarray:
    """Collapse (time, lev, lat, lon) to (lat, lon) using first slice of time & lev.

    Most MOSDAC daily L4 products are 4D with time=1 and lev=1.
    """
    if arr.ndim == 4:
        return arr[0, 0, :, :]
    if arr.ndim == 3:
        return arr[0, :, :]
    if arr.ndim == 2:
        return arr
    raise ValueError(f"Cannot collapse array of shape {arr.shape}")


def _open_dataset(path, file_type: str):
    """Open a parsed file as an xarray dataset using the right engine."""
    import xarray as xr
    if file_type in ("NetCDF3", "NetCDF4", "HDF5"):
        engine = "netcdf4"
    else:
        engine = "scipy"
    return xr.open_dataset(path, engine=engine)


# ----------------------------------------------------------------------
# Chlorophyll
# ----------------------------------------------------------------------

def extract_chlorophyll(pf, lat: float, lon: float, debug: bool = False) -> dict[str, Any] | None:
    """Extract chlorophyll-a concentration at (lat, lon).

    Handles both JPSS2/VIIRS files (variable: chlor_a, lon -180 to 180)
    and EOS-06/OCM files (variable: chlorophyll_concentration or similar).

    Returns:
        {
            "value": float,            # mg/m^3
            "units": "mg m^-3",
            "lat": float, lon: float,  # grid point
            "distance_deg": float,
            "source": str,
            "log": float,              # log10(value) for plotting
        }
    """
    if "chlor_a" not in pf.variables and not any(
        "chlor" in v.lower() for v in pf.variables
    ):
        return None

    # Find chlorophyll variable (most common: chlor_a)
    var_name = next(
        (v for v in pf.variables if "chlor" in v.lower()),
        "chlor_a",
    )

    try:
        with _open_dataset(pf.path, pf.file_type) as ds:
            lats = ds.coords.get("lat", ds.coords.get("latitude"))
            lons = ds.coords.get("lon", ds.coords.get("longitude"))
            if lats is None or lons is None:
                return None
            lats_v = lats.values
            lons_v = lons.values

            # Normalize request longitude to file's convention
            if lons_v.min() >= 0:
                target_lon = _normalize_lon(lon)
            else:
                target_lon = lon

            lat_idx = _nearest_index(lats_v, lat)
            lon_idx = _nearest_index(lons_v, target_lon)
            found_lat = float(lats_v[lat_idx])
            found_lon = float(lons_v[lon_idx])

            # If file uses 0-360, convert back to -180-180 for display
            display_lon = found_lon if found_lon <= 180 else found_lon - 360

            dist = math.hypot(found_lat - lat, display_lon - lon)
            if dist > 2.0:
                return None

            arr = ds[var_name].values
            arr2d = _collapse_4d(arr)

            # Resolve _FillValue once. NASA L3 SMI files set this via the
            # encoding dict (not just attrs). Examples we've seen: 9999.0,
            # -32767.0, 1e30. Sentinel values that match _FillValue exactly
            # are land/missing and must be treated as NaN.
            fill_values = set()
            for src in (ds[var_name].encoding, ds[var_name].attrs):
                for key in ('_FillValue', 'missing_value', 'fill_value'):
                    if key in src:
                        try:
                            fill_values.add(float(src[key]))
                        except (TypeError, ValueError):
                            pass
            # Common L3 sentinels if not declared
            fill_values.update({9999.0, -32767.0, -9999.0, 1e30, -1e30})

            def _apply_fill_mask(v: float) -> float:
                """Replace fill-value sentinels with NaN."""
                if math.isnan(v):
                    return float('nan')
                for fv in fill_values:
                    if abs(v - fv) < 1e-3:
                        return float('nan')
                return v

            value = _apply_fill_mask(float(arr2d[lat_idx, lon_idx]))

            # If the nearest cell is masked, search a wider ring of
            # neighbours. NASA L3 files have aggressive land masking
            # AND heavy cloud masking — single-day files can have <20%
            # valid coverage. We look up to 10x10 (about 100 km radius
            # for 9km grid) and return the nearest valid cell.
            if math.isnan(value):
                best = None
                best_dist = float('inf')
                # Spiral search outward
                for r in range(1, 11):
                    found_any = False
                    for dlat in range(-r, r + 1):
                        for dlon in range(-r, r + 1):
                            # Only cells on the edge of the current ring
                            if max(abs(dlat), abs(dlon)) != r:
                                continue
                            ni, nj = lat_idx + dlat, lon_idx + dlon
                            if 0 <= ni < arr2d.shape[0] and 0 <= nj < arr2d.shape[1]:
                                v = _apply_fill_mask(float(arr2d[ni, nj]))
                                if not math.isnan(v) and v >= 0:
                                    cell_dist = math.hypot(
                                        float(lats_v[ni]) - lat,
                                        float(lons_v[nj]) - lon
                                    )
                                    if cell_dist < best_dist:
                                        best = v
                                        best_dist = cell_dist
                                        found_any = True
                    if found_any:
                        value = best
                        dist = best_dist  # update reported distance
                        found_lat = float(lats_v[lat_idx])  # keep grid anchor
                        found_lon = float(lons_v[lon_idx])
                        display_lon = found_lon if found_lon <= 180 else found_lon - 360
                        break

            # Mask fill / nan / negative chlorophyll.
            if math.isnan(value):
                if debug:
                    return {
                        "value": float('nan'),
                        "units": "mg m^-3",
                        "lat": found_lat,
                        "lon": display_lon,
                        "distance_deg": float(dist),
                        "source": pf.path.name,
                        "debug": "cell is NaN (land or fill value)",
                        "grid_index": [int(lat_idx), int(lon_idx)],
                    }
                return None
            if value < 0:
                if debug:
                    return {
                        "value": value,
                        "units": "mg m^-3",
                        "lat": found_lat,
                        "lon": display_lon,
                        "distance_deg": float(dist),
                        "source": pf.path.name,
                        "debug": f"cell is negative ({value}) — likely fill value",
                    }
                return None
            if value > 1000:  # L3 maxes are usually <100 mg/m^3
                if debug:
                    return {
                        "value": value,
                        "units": "mg m^-3",
                        "lat": found_lat,
                        "lon": display_lon,
                        "distance_deg": float(dist),
                        "source": pf.path.name,
                        "debug": f"cell is >1000 ({value}) — likely fill value",
                    }
                return None
            # If very small (< 0.001), treat as below detection → still return it
            # but mark as "below detection" so the caller can decide.

            return {
                "value": value,
                "units": pf.variables[var_name].get("units", "mg m^-3"),
                "lat": found_lat,
                "lon": display_lon,
                "distance_deg": float(dist),
                "source": pf.path.name,
                "log": math.log10(value) if value > 0 else None,
                "valid": value >= 0.001,  # flag for caller
            }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "source": pf.path.name}


# ----------------------------------------------------------------------
# Wind
# ----------------------------------------------------------------------

def extract_wind(pf, lat: float, lon: float) -> dict[str, Any] | None:
    """Extract analyzed wind vector and derived fields at (lat, lon).

    Returns speed (m/s), direction (deg, meteorological convention: 0 = N,
    90 = E, blowing FROM), plus zonal/meridional components, stress, curl.

    Returns:
        {
            "u": float, "v": float,        # zonal/meridional wind (m/s)
            "speed": float,                  # m/s
            "direction_deg": float,          # meteorological, 0=N, 90=E
            "tau_x": float, "tau_y": float,  # wind stress (Pa)
            "curl": float,                   # wind stress curl (Pa/m)
            "samples": int,                  # data quality
            "lat": float, "lon": float,
            "distance_deg": float,
            "source": str,
        }
    """
    if "U" not in pf.variables or "V" not in pf.variables:
        return None

    try:
        with _open_dataset(pf.path, pf.file_type) as ds:
            lats = ds.coords.get("lat", ds.coords.get("latitude"))
            lons = ds.coords.get("lon", ds.coords.get("longitude"))
            lats_v = lats.values
            lons_v = lons.values

            # 0-360 longitude convention
            target_lon = _normalize_lon(lon)
            lat_idx = _nearest_index(lats_v, lat)
            lon_idx = _nearest_index(lons_v, target_lon)
            found_lat = float(lats_v[lat_idx])
            found_lon = float(lons_v[lon_idx])
            display_lon = found_lon if found_lon <= 180 else found_lon - 360

            dist = math.hypot(found_lat - lat, display_lon - lon)
            if dist > 2.0:
                return None

            def get_var(name: str) -> float | None:
                if name not in pf.variables:
                    return None
                arr = _collapse_4d(ds[name].values)
                val = float(arr[lat_idx, lon_idx])
                if math.isnan(val):
                    return None
                return val

            u = get_var("U")
            v = get_var("V")
            if u is None or v is None:
                return None

            speed = math.hypot(u, v)
            # Meteorological convention: direction wind is BLOWING FROM.
            # atan2 of (u, v) gives direction wind is BLOWING TOWARDS (east = 0, north = 90).
            # To convert: meteorological_dir = (270 - atan2_deg) mod 360
            direction_towards = math.degrees(math.atan2(v, u))
            # atan2(v, u) returns angle from east axis, going counter-clockwise.
            # We want meteorological: 0 = from North, 90 = from East.
            # dir_towards is direction wind is going (vector direction).
            # meteorological_from = (dir_towards + 180) mod 360
            met_from = (direction_towards + 180) % 360

            result = {
                "u": u,
                "v": v,
                "speed": speed,
                "direction_deg": met_from,
                "lat": found_lat,
                "lon": display_lon,
                "distance_deg": float(dist),
                "source": pf.path.name,
            }
            # Optional fields
            taux = get_var("TAUX")
            tauy = get_var("TAUY")
            if taux is not None and tauy is not None:
                result["tau_x"] = taux
                result["tau_y"] = tauy
            curl = get_var("CURL")
            if curl is not None:
                result["curl"] = curl
            samples = get_var("NS")
            if samples is not None:
                result["samples"] = int(samples)
            return result
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "source": pf.path.name}


# ----------------------------------------------------------------------
# Wind — L2B swath products (E06SCT_L2B_WV12 / WV25)
# ----------------------------------------------------------------------

# Candidate variable names, checked case-insensitively against the LAST
# path segment (swath arrays can live inside HDF5 subgroups). Names are
# learned from MOSDAC/SCATSAT heritage products; the deep dump
# (pipeline/deepdump.py) prints the real inventory so this list can be
# corrected against evidence instead of guesses.
_SWATH_LAT_NAMES = ("lat", "latitude")
_SWATH_LON_NAMES = ("lon", "longitude")
_U_NAMES = ("u10", "u_wind", "uwind", "zonal_wind", "u")
_V_NAMES = ("v10", "v_wind", "vwind", "meridional_wind", "v")
_SPEED_NAMES = ("wind_speed", "windspeed", "wspd", "speed")
_DIR_NAMES = ("wind_dir", "winddir", "wdir", "direction")
_FLAG_NAMES = ("quality_flag", "quality", "qc", "flag", "wvc_quality")


def _decode_swath_array(arr: np.ndarray, attrs: dict) -> np.ndarray:
    """Apply HDF/NetCDF packing (scale_factor/add_offset) + fill mask.

    Swath geolocation is commonly stored as packed int16 — reading it raw
    is exactly how 'no usable latitude/longitude' verdicts happen.
    """
    out = np.asarray(arr, dtype=np.float64)
    scale = add = None
    for k, v in (attrs or {}).items():
        kl = str(k).lower()
        try:
            if kl == "scale_factor" and scale is None:
                scale = float(np.asarray(v).ravel()[0])
            elif kl == "add_offset" and add is None:
                add = float(np.asarray(v).ravel()[0])
        except Exception:  # noqa: BLE001
            pass
    if scale is not None or add is not None:
        out = out * (scale if scale is not None else 1.0) + (add if add is not None else 0.0)
    fills = set()
    for k, v in (attrs or {}).items():
        kl = str(k).lower()
        if kl in ("_fillvalue", "fill_value", "missing_value"):
            try:
                fills.add(float(np.asarray(v).ravel()[0]))
                # packed fill decodes too — record the RAW fill as well
                if scale is not None or add is not None:
                    raw = float(np.asarray(v).ravel()[0])
                    fills.add(raw * (scale if scale is not None else 1.0)
                              + (add if add is not None else 0.0))
            except Exception:  # noqa: BLE001
                pass
    for fv in fills:
        out[np.isclose(out, fv, rtol=1e-6, atol=1e-6)] = np.nan
    out[~np.isfinite(out)] = np.nan
    return out


def _find_swath_var(pf, names: tuple[str, ...], want_2d: bool = True):
    """Locate a swath variable by candidate base names.

    Returns (path, opener) where opener() -> (np.ndarray values, attrs dict).
    Prefers paths the parser already flagged (pf.swath_lat / swath_lon).
    """
    import h5py

    def _open(path):
        if pf.file_type == "HDF5" or str(pf.path).lower().endswith((".h5", ".hdf5", ".he5")):
            with h5py.File(pf.path, "r") as f:
                obj = f[path]
                return np.array(obj[()]), {k: obj.attrs[k] for k in obj.attrs}
        with _open_dataset(pf.path, pf.file_type) as ds:
            return ds[path].values, {k: ds[path].attrs[k] for k in ds[path].attrs}

    lowered = {v.lower(): v for v in pf.variables}
    for cand in names:
        if cand in lowered:
            path = lowered[cand]
            info = pf.variables[path]
            shape = info.get("shape") or info.get("dims") or []
            if want_2d and len(shape) != 2:
                continue
            return path, _open
    # fall back to base-name matching on the last path segment
    for path, info in pf.variables.items():
        base = path.split("/")[-1].lower()
        if base in names:
            shape = info.get("shape") or []
            if want_2d and len(shape) != 2:
                continue
            return path, _open
    return None, _open


def extract_wind_swath(pf, lat: float, lon: float,
                       max_dist_deg: float = 1.0) -> dict[str, Any] | None:
    """Wind at (lat, lon) from an L2B SWATH granule (per-pixel geolocation).

    Why this exists (2026-09-13): E06SCT_L2B_WV12 HDF5 files carry wind
    vectors on the satellite swath — latitude/longitude are 2D per-pixel
    arrays (often packed int16 with scale_factor), NOT 1D grid
    coordinates. extract_wind() only understands regular grids and
    returns None for these files, which got mis-reported as the product
    "lacking usable latitude/longitude". The arrays are there; this
    extractor reads them.

    Returns the same shape as extract_wind() plus `flag` (raw quality
    value at the pixel — semantics confirmed from the real file before
    any agent wiring; we never mask on a guessed flag meaning).
    """
    try:
        lat_path, opener = _find_swath_var(pf, _SWATH_LAT_NAMES)
        lon_path = None
        if lat_path:
            lon_path, _ = _find_swath_var(pf, _SWATH_LON_NAMES)
        if not lat_path or not lon_path:
            return None

        lat_arr, lat_attrs = opener(lat_path)
        lon_arr, lon_attrs = opener(lon_path)
        lat_d = _decode_swath_array(lat_arr, lat_attrs)
        lon_d = _decode_swath_array(lon_arr, lon_attrs)
        if lat_d.shape != lon_d.shape or lat_d.ndim != 2:
            return None

        # 0-360 vs -180..180 convention: match the file, not the caller
        lon_shift = float(np.nanmean(lon_d)) > 180.0
        target_lon = _normalize_lon(lon) if lon_shift else lon

        # Nearest pixel: coarse subsample first, then refine locally —
        # a 12 km swath grid has millions of pixels, argmin over the
        # full array is needlessly slow.
        n = lat_d.size
        step = max(1, int(n ** 0.5 / 220))
        sub_lat = lat_d[::step, ::step]
        sub_lon = lon_d[::step, ::step]
        ok = np.isfinite(sub_lat) & np.isfinite(sub_lon)
        if not ok.any():
            return None
        d2 = (sub_lat - lat) ** 2
        dlon = np.abs(sub_lon - target_lon)
        dlon = np.minimum(dlon, 360.0 - dlon)   # handle the 0/360 seam
        d2 = d2 + dlon ** 2
        d2[~ok] = np.inf
        r0, c0 = np.unravel_index(int(np.argmin(d2)), d2.shape)
        # refine in a window around the coarse hit
        rr = slice(max(0, r0 * step - step), min(lat_d.shape[0], r0 * step + 2 * step))
        cc = slice(max(0, c0 * step - step), min(lat_d.shape[1], c0 * step + 2 * step))
        win_lat = lat_d[rr, cc]
        win_lon = lon_d[rr, cc]
        ok = np.isfinite(win_lat) & np.isfinite(win_lon)
        if not ok.any():
            return None
        d2 = (win_lat - lat) ** 2 + np.minimum(np.abs(win_lon - target_lon),
                                               360.0 - np.abs(win_lon - target_lon)) ** 2
        d2[~ok] = np.inf
        wi, wj = np.unravel_index(int(np.argmin(d2)), d2.shape)
        pix_r = rr.start + int(wi)
        pix_c = cc.start + int(wj)
        found_lat = float(lat_d[pix_r, pix_c])
        found_lon = float(lon_d[pix_r, pix_c])
        disp_lon = found_lon - 360.0 if (lon_shift and found_lon > 180) else found_lon

        dlon_disp = abs(disp_lon - lon)
        dlon_disp = min(dlon_disp, 360.0 - dlon_disp)
        dist = math.hypot(found_lat - lat, dlon_disp)
        if dist > max_dist_deg:
            return None

        def _val(path):
            if path is None:
                return None
            try:
                arr, attrs = opener(path)
                dec = _decode_swath_array(arr, attrs)
                if dec.ndim != 2:
                    return None
                v = float(dec[pix_r, pix_c])
                return v if math.isfinite(v) else None
            except Exception:  # noqa: BLE001
                return None

        u_path, _ = _find_swath_var(pf, _U_NAMES, want_2d=False)
        v_path, _ = _find_swath_var(pf, _V_NAMES, want_2d=False)
        spd_path, _ = _find_swath_var(pf, _SPEED_NAMES, want_2d=False)
        dir_path, _ = _find_swath_var(pf, _DIR_NAMES, want_2d=False)

        u = v = None
        if u_path and v_path:
            u, v = _val(u_path), _val(v_path)
        if (u is None or v is None) and spd_path and dir_path:
            spd = _val(spd_path)
            drc = _val(dir_path)
            if spd is not None and drc is not None:
                # meteorological FROM convention (0=N, 90=E) — the
                # standard for scatterometer wind direction
                rad = math.radians(drc)
                u = -spd * math.sin(rad)
                v = -spd * math.cos(rad)
        if u is None or v is None:
            return None

        speed = math.hypot(u, v)
        met_from = (math.degrees(math.atan2(v, u)) + 180.0) % 360.0
        result = {
            "u": u,
            "v": v,
            "speed": speed,
            "direction_deg": met_from,
            "lat": found_lat,
            "lon": disp_lon,
            "distance_deg": float(dist),
            "pixel": (pix_r, pix_c),
            "source": pf.path.name,
        }
        if spd_path:
            s = _val(spd_path)
            if s is not None:
                result["speed_reported"] = s
        flag_path, _ = _find_swath_var(pf, _FLAG_NAMES, want_2d=False)
        if flag_path:
            try:
                arr, attrs = opener(flag_path)
                result["flag"] = int(arr[pix_r, pix_c])
                result["flag_var"] = flag_path
            except Exception:  # noqa: BLE001
                pass
        return result
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "source": pf.path.name}


# ----------------------------------------------------------------------
# Upwelling
# ----------------------------------------------------------------------

def extract_upwelling(pf, lat: float, lon: float) -> dict[str, Any] | None:
    """Extract upwelling index at (lat, lon).

    Units: m^2/s. Positive = upwelling (cold nutrient-rich water rising).

    Returns:
        {
            "value": float,        # m^2/s
            "units": "m^2/s",
            "lat": float, "lon": float,
            "distance_deg": float,
            "source": str,
            "interpretation": str,  # "strong upwelling" / "downwelling" / etc.
        }
    """
    # Variable is "Upwelling_index" (capital U) in MOSDAC EOS-06 files
    var_name = next(
        (v for v in pf.variables if "upwelling" in v.lower()),
        None,
    )
    if var_name is None:
        return None

    try:
        with _open_dataset(pf.path, pf.file_type) as ds:
            lats = ds.coords.get("lat", ds.coords.get("latitude"))
            lons = ds.coords.get("lon", ds.coords.get("longitude"))
            lats_v = lats.values
            lons_v = lons.values

            target_lon = _normalize_lon(lon)
            lat_idx = _nearest_index(lats_v, lat)
            lon_idx = _nearest_index(lons_v, target_lon)
            found_lat = float(lats_v[lat_idx])
            found_lon = float(lons_v[lon_idx])
            display_lon = found_lon if found_lon <= 180 else found_lon - 360

            dist = math.hypot(found_lat - lat, display_lon - lon)
            if dist > 2.0:
                return None

            arr = _collapse_4d(ds[var_name].values)
            value = float(arr[lat_idx, lon_idx])

            # Mask fill value (-1e6) and nan
            if math.isnan(value) or value <= _UPWELLING_FILL / 2:
                return None

            # Interpretation thresholds
            if value > 50:
                interp = "strong upwelling"
            elif value > 10:
                interp = "moderate upwelling"
            elif value > -10:
                interp = "neutral / weak"
            elif value > -50:
                interp = "moderate downwelling"
            else:
                interp = "strong downwelling"

            return {
                "value": value,
                "units": pf.variables[var_name].get("units", "m^2/s"),
                "lat": found_lat,
                "lon": display_lon,
                "distance_deg": float(dist),
                "source": pf.path.name,
                "interpretation": interp,
            }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "source": pf.path.name}
