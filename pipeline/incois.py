"""INCOIS (Indian National Centre for Ocean Information Services) adapter.

INCOIS publishes Indian Ocean chlorophyll from OCEANSAT-2 OCM and
Oceansat-3 OCM-3, plus daily Potential Fishing Zone (PFZ) advisories
for 586 fish landing centers along the Indian coast.

INTEGRATION STATUS (2026-09-04):
  - OPeNDAP THREDDS (las.incois.gov.in):  USED, but as a SAFE point-query
    backup only. History lesson: the first version loaded the ENTIRE
    global OCM-2 array into RAM (GBs) and OOM-crashed the backend on the
    user's laptop mid-request. The current version asks the OPeNDAP
    server for a tiny ~0.6° hyperslab (KBs over the wire, not GBs), so
    memory risk is gone. The server itself is still often slow or down
    from outside India — hence "backup": it only runs when NOAA and
    OC-CCI BOTH failed, never in the hot path.
  - PFZ advisory:  we use the WORKING official feed (GeoServer WFS,
    pipeline/incois_pfz.py) — that's the INCOIS product fishers
    actually use daily.
  - ERDDAP (erddap.incois.gov.in):  NO chlorophyll dataset — AMSR-E SST
    (stale 2011), ASCAT winds, ARGO, OISST only.

Nothing here is faked: if INCOIS OPeNDAP fails, the caller shows the
real error and falls back to NOAA / OC-CCI / MOSDAC (creds) instead.
"""
from __future__ import annotations

import os
from typing import Any


# INCOIS OCM-2 OPeNDAP URL (flaky server — we only point-query it now)
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
    timeout_sec: float = 12.0,
    box_deg: float = 0.3,
) -> dict[str, Any] | None:
    """Point-query INCOIS OPeNDAP for chlorophyll near (lat, lon).

    CRASH-SAFE by construction: we subset server-side with .sel() so
    OPeNDAP transfers only the small hyperslab (~0.6° box ≈ a few KB),
    never the multi-GB global grid. (The 2026-09-03 laptop crash was
    `ds[var].values` on the FULL array — that code is deleted.)

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
            subset = ds[var_name].sel({lat_name: lat_slice, lon_name: lon_slice})
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
                "source": "INCOIS OCM-2 (OPeNDAP point subset)",
                "note": f"safe hyperslab ~{2 * box_deg:.1f}° box, {arr.size} cells — "
                        "not the full global grid",
            }
    except _Timeout as e:
        return {"error": str(e), "source": SOURCE_LABEL}
    except Exception as e:  # noqa: BLE001
        return {
            "error": f"INCOIS OPeNDAP: {type(e).__name__}: {str(e)[:100]}",
            "source": SOURCE_LABEL,
        }
    finally:
        if old_handler is not None and hasattr(signal, "SIGALRM"):
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)


def get_chlorophyll(
    lat: float,
    lon: float,
    date: str | None = "2026-08-15",
    timeout_sec: float = 12.0,
) -> dict[str, Any] | None:
    """Chlorophyll from INCOIS — safe point-query, backup role.

    Called ONLY when NOAA ERDDAP and ESA OC-CCI both failed (the caller,
    pipeline/orca_data.py, decides). Returns an honest error dict when
    the flaky server doesn't answer — we never invent a value.
    `date` is accepted for interface parity; the OCM-2 OPeNDAP archive
    is effectively a climatological grid, so the returned value is a
    spatial mean around the point, flagged in `note`.
    """
    if not _opendap_enabled():
        return {
            "error": "INCOIS OPeNDAP disabled via ORCA_INCOIS_OPENDAP=0",
            "source": SOURCE_LABEL,
        }
    return _try_opendap_chl(lat, lon, timeout_sec=timeout_sec)


def get_sst(
    lat: float,
    lon: float,
    date: str | None = "2026-08-15",
) -> dict[str, Any] | None:
    """INCOIS doesn't expose machine-readable SST. Use Open-Meteo instead."""
    return {
        "error": "INCOIS SST endpoint not available. Use Open-Meteo Marine.",
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
        "opendap_known_issue": "Server is frequently slow/down from outside India — used as backup only",
        "erddap_url": INCOIS_ERDDAP_URL,
        "erddap_datasets": "15 griddap datasets, none for chlorophyll",
        "pfz_url": INCOIS_PFZ_URL,
        "pfz_note": "PFZ lines come from the WORKING INCOIS GeoServer WFS (pipeline/incois_pfz.py)",
        "recommendation": (
            "Primary chlorophyll: NOAA ERDDAP (global NRT). Cross-check: ESA OC-CCI. "
            "Indian Ocean 🇮🇳: MOSDAC OCM-3 with credentials. INCOIS OPeNDAP stays a "
            "safe point-subset backup (server itself is flaky); the WORKING INCOIS "
            "product we rely on is the daily official PFZ WFS feed."
        ),
    }
