"""INCOIS (Indian National Centre for Ocean Information Services) adapter.

INCOIS publishes Indian Ocean chlorophyll from OCEANSAT-2 OCM and
Oceansat-3 OCM-3, plus daily Potential Fishing Zone (PFZ) advisories
for 586 fish landing centers along the Indian coast.

INTEGRATION STATUS (audited 2026-09-12):
  - OPeNDAP THREDDS (las.incois.gov.in): conditional point-query backup.
    The first version loaded the entire array into RAM. The current adapter
    requests a small spatial hyperslab and now requires a verifiable temporal
    coordinate/date before returning a value. The forced audit in this runtime
    returned a measured NetCDF I/O failure; that is not a global-liveness claim.
  - PFZ advisory:  a separate official GeoServer WFS adapter is wired
    pipeline/incois_pfz.py) — that's the INCOIS product fishers
    actually use daily.
  - ERDDAP (erddap.incois.gov.in):  NO chlorophyll dataset — AMSR-E SST
    (stale 2011), ASCAT winds, ARGO, OISST only.

Nothing here is fabricated: a transport, schema, temporal-match, or no-pixel
failure is returned as unavailable with its measured reason.
"""
from __future__ import annotations

import os
from typing import Any


# INCOIS OCM-2 OPeNDAP URL; the adapter only performs bounded point queries.
INCOIS_OPENDAP_BASE = (
    "http://las.incois.gov.in/thredds/id-b36be55868/"
    "data_home_las_datasets_oceancolour_Oceansat2-OCM.nc.jnl"
)

# INCOIS public PFZ advisory page (humans can read, machines cannot)
INCOIS_PFZ_URL = "https://www.incois.gov.in/MarineFisheries/PfzAdvisory"

# INCOIS ERDDAP (no chlorophyll but has other datasets)
INCOIS_ERDDAP_URL = "https://erddap.incois.gov.in/erddap/"

# Source label shown in the UI
SOURCE_LABEL = "INCOIS"


def _opendap_enabled() -> bool:
    """OPeNDAP backup is ON by default now that it's a safe hyperslab
    point-query (the GBs-into-RAM crash path is gone). Set
    ORCA_INCOIS_OPENDAP=0 to disable completely."""
    return os.environ.get("ORCA_INCOIS_OPENDAP", "1") != "0"


def _try_opendap_chl(
    lat: float,
    lon: float,
    target_date: str | None,
    timeout_sec: float = 12.0,
    box_deg: float = 0.3,
    max_date_gap_days: int = 7,
) -> dict[str, Any] | None:
    """Point-query INCOIS OPeNDAP for chlorophyll near (lat, lon).

    The data variable must expose a decodable time coordinate. A requested
    date is matched to the nearest available observation within
    ``max_date_gap_days`` and the actual selected date is returned. Without
    that evidence, the source remains unavailable rather than being labelled
    with the requested date.

    The spatial subset is selected before values are loaded, avoiding the old
    full-array path.

    Hard-capped at timeout_sec via SIGALRM when on the main thread; in
    worker threads the caller's future timeout abandons us (the
    leftover socket closes harmlessly).
    """
    try:
        import numpy as np
        import xarray as xr
    except ImportError:
        return {"error": "xarray/netCDF4 not installed", "source": SOURCE_LABEL}

    import signal
    import threading

    class _Timeout(Exception):
        pass

    def _alarm_handler(signum, frame):
        raise _Timeout(f"INCOIS OPeNDAP timed out after {timeout_sec:.0f}s")

    old_handler = None
    on_main_thread = threading.current_thread() is threading.main_thread()
    if on_main_thread and hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_sec)

    try:
        with xr.open_dataset(INCOIS_OPENDAP_BASE, engine="netcdf4") as ds:
            var_name = None
            for cand in ("CHL", "chl", "chlor_a", "chlorophyll", "chlorophyll-a"):
                if cand in ds.data_vars:
                    var_name = cand
                    break
            if var_name is None:
                return {
                    "error": f"INCOIS dataset has no chlorophyll var. Vars: {list(ds.data_vars)[:5]}",
                    "source": SOURCE_LABEL,
                }

            lat_name = "lat" if "lat" in ds.coords else "latitude"
            lon_name = "lon" if "lon" in ds.coords else "longitude"
            if lat_name not in ds.coords or lon_name not in ds.coords:
                return {"error": "INCOIS dataset missing lat/lon coords", "source": SOURCE_LABEL}

            variable = ds[var_name]
            time_name = None
            for dim in variable.dims:
                coord = ds.coords.get(dim)
                standard_name = str(getattr(coord, "attrs", {}).get("standard_name", "")).lower()
                if dim.lower() in {"time", "date", "datetime"} or standard_name == "time":
                    time_name = dim
                    break
            if time_name is None or time_name not in ds.coords:
                return {
                    "error": "INCOIS dataset has no verifiable time coordinate",
                    "source": SOURCE_LABEL,
                }

            try:
                time_values = np.asarray(ds.coords[time_name].values).astype("datetime64[ns]")
                valid_indices = np.flatnonzero(~np.isnat(time_values))
                if valid_indices.size == 0:
                    raise ValueError("time coordinate is empty or undecodable")
                valid_times = time_values[valid_indices]
                if target_date:
                    target = np.datetime64(target_date, "ns")
                    deltas = np.abs(valid_times - target)
                    relative_index = int(np.argmin(deltas))
                    time_index = int(valid_indices[relative_index])
                    gap_days = float(deltas[relative_index] / np.timedelta64(1, "D"))
                    if gap_days > max_date_gap_days:
                        return {
                            "error": (
                                f"INCOIS nearest observation is {gap_days:.1f} days from "
                                f"requested date (limit {max_date_gap_days} days)"
                            ),
                            "source": SOURCE_LABEL,
                        }
                else:
                    time_index = int(valid_indices[int(np.argmax(valid_times))])
                actual_time = time_values[time_index]
                actual_date = np.datetime_as_string(actual_time, unit="D")
                variable = variable.isel({time_name: time_index})
            except Exception as exc:  # noqa: BLE001
                return {
                    "error": f"INCOIS time coordinate could not be matched: {type(exc).__name__}: {exc}",
                    "source": SOURCE_LABEL,
                }

            extra_dims = [d for d in variable.dims if d not in {lat_name, lon_name}]
            for dim in extra_dims:
                if variable.sizes.get(dim) != 1:
                    return {
                        "error": f"INCOIS chlorophyll has unsupported dimension {dim}",
                        "source": SOURCE_LABEL,
                    }
                variable = variable.isel({dim: 0})

            # Respect coordinate direction (ascending vs descending) or
            # .sel() with a (lo, hi) slice returns an EMPTY selection.
            lat_vals = ds.coords[lat_name].values
            lon_vals = ds.coords[lon_name].values
            lat_desc = len(lat_vals) > 1 and lat_vals[0] > lat_vals[-1]
            lon_desc = len(lon_vals) > 1 and lon_vals[0] > lon_vals[-1]
            lat_slice = (slice(lat + box_deg, lat - box_deg) if lat_desc
                         else slice(lat - box_deg, lat + box_deg))
            lon_slice = (slice(lon + box_deg, lon - box_deg) if lon_desc
                         else slice(lon - box_deg, lon + box_deg))

            # THE SAFE SUBSET — OPeNDAP hyperslab, KBs on the wire.
            subset = variable.sel({lat_name: lat_slice, lon_name: lon_slice})
            arr = np.asarray(subset.values, dtype="float64").ravel()
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                return {
                    "error": f"INCOIS subset around ({lat:.2f},{lon:.2f}) had no valid cells",
                    "source": SOURCE_LABEL,
                }
            return {
                "value": float(arr.mean()),
                "units": ds[var_name].attrs.get("units", "mg m^-3"),
                "n_cells": int(arr.size),
                "lat": lat,
                "lon": lon,
                "box_deg": box_deg,
                "date": actual_date,
                "source": "INCOIS OCM-2 (OPeNDAP point subset)",
                "note": (
                    f"spatial hyperslab ~{2 * box_deg:.1f}° box, {arr.size} cells; "
                    f"selected observation date {actual_date}"
                ),
            }
    except _Timeout as e:
        return {"error": str(e), "source": SOURCE_LABEL}
    except Exception as e:  # noqa: BLE001
        return {
            "error": f"INCOIS OPeNDAP: {type(e).__name__}: {str(e)[:300]}",
            "source": SOURCE_LABEL,
        }
    finally:
        if old_handler is not None and hasattr(signal, "SIGALRM"):
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)


def get_chlorophyll(
    lat: float,
    lon: float,
    date: str | None = None,
    timeout_sec: float = 12.0,
) -> dict[str, Any] | None:
    """Chlorophyll from INCOIS — safe point-query, backup role.

    Called only when NOAA ERDDAP and ESA OC-CCI both failed (the caller,
    pipeline/orca_data.py, decides). Returns an error dict for transport,
    schema, temporal-match, or no-valid-cell failure. ``date`` is used for a
    bounded nearest-time match, and the actual selected date is returned.
    """
    if not _opendap_enabled():
        return {
            "error": "INCOIS OPeNDAP disabled via ORCA_INCOIS_OPENDAP=0",
            "source": SOURCE_LABEL,
        }
    return _try_opendap_chl(lat, lon, date, timeout_sec=timeout_sec)


def get_sst(
    lat: float,
    lon: float,
    date: str | None = None,
) -> dict[str, Any] | None:
    """SST is not implemented by this INCOIS adapter."""
    return {
        "error": "INCOIS SST is not implemented in the current ORCA adapter",
        "source": SOURCE_LABEL,
        "alternative": "https://open-meteo.com/",
    }


def status() -> dict[str, Any]:
    """Return the current INCOIS integration status (for debugging)."""
    return {
        "opendap_url": INCOIS_OPENDAP_BASE,
        "opendap_mode": "safe point-hyperslab (~0.6° box) — no full-array RAM load",
        "opendap_enabled_by_default": True,
        "opendap_disable_hint": "export ORCA_INCOIS_OPENDAP=0 to disable the backup query",
        "opendap_known_issue": "Live audit returned NetCDF I/O failure in this runtime — used as backup only",
        "erddap_url": INCOIS_ERDDAP_URL,
        "erddap_datasets": "15 griddap datasets, none for chlorophyll",
        "pfz_url": INCOIS_PFZ_URL,
        "pfz_note": "PFZ lines use the INCOIS GeoServer WFS adapter (pipeline/incois_pfz.py); availability is checked per request",
        "role": (
            "Conditional chlorophyll point-subset backup after NOAA and OC-CCI; "
            "official PFZ WFS availability is reported separately per request."
        ),
    }
