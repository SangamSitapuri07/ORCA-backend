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
