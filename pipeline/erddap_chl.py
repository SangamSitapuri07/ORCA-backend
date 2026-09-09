"""NOAA ERDDAP adapter — real-time chlorophyll from VIIRS.

NOAA's CoastWatch ERDDAP server provides free, public, near-real-time
chlorophyll-a from the JPSS VIIRS instruments. No authentication, no
API keys — just HTTP queries.

Primary dataset: NOAA S-NPP + NOAA-20 VIIRS, NRT, Global 9km, 2020-present
URL: https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSDINEOFDaily

Variable: chlor_a (Chlorophyll Concentration, DINEOF Gap-Filled, mg m^-3)

Key feature: DINEOF (Data INterpolating Empirical Orthogonal Functions)
algorithm reconstructs values under clouds and missing data. This
solves the cloud-masking problem that plagued our single-day L3 files
from MOSDAC/JPSS2.

Implementation note: We use the .csv endpoint instead of .nc because
ERDDAP's netCDF subsetter is strict about the constraint syntax,
but the CSV endpoint accepts simpler queries and returns the same
data in a more forgiving format. We parse the CSV with Python's
built-in csv module — no xarray/netCDF4 needed for this adapter.
"""
from __future__ import annotations

import csv
import io
import math
import urllib.request
from datetime import datetime, timedelta
from typing import Any


# The DINEOF gap-filled chlorophyll dataset
ERDDAP_BASE = "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSDINEOFDaily"

# Backup datasets for fallback
ERDDAP_BACKUPS = {
    "viirs_dineof_2km": "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20S3ASCIDINEOF2kmDaily",
    "viirs_dineof_9km_sq": "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSSCIDINEOFDaily",
    "viirs_dineof_9km": "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20S3ASCIDINEOFDaily",
    "viirs_oci_nrt": "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSchlociDaily",
    "viirs_oc3_nrt": "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSchlaDaily",
}


def build_query_url(
    lat: float,
    lon: float,
    date: str | datetime | None = None,
    radius_deg: float = 0.1,
    variable: str = "chlor_a",
    ext: str = ".csv",
) -> str:
    """Build an ERDDAP .csv query URL to extract chlorophyll near (lat, lon).

    The 4D axis order is: time, altitude, latitude, longitude.
    Even though altitude is a singleton (0.0 only), it MUST be in the URL.

    Args:
        lat: Latitude (-90 to 90)
        lon: Longitude (-180 to 180)
        date: Specific date as YYYY-MM-DD (default: [last] for most recent)
        radius_deg: Half-width of the box to extract (default 0.1° = ~10km)
        variable: Variable name (default chlor_a)
        ext: File extension (default .csv — most reliable)
    """
    if date is None:
        time_constraint = "last"
    elif isinstance(date, datetime):
        date_str = date.strftime("%Y-%m-%d")
        time_constraint = f"({date_str}T12:00:00Z):1:({date_str}T12:00:00Z)"
    else:
        time_constraint = f"({str(date)}T12:00:00Z):1:({str(date)}T12:00:00Z)"

    target_lon = lon

    lat_lo = lat - radius_deg
    lat_hi = lat + radius_deg
    lon_lo = target_lon - radius_deg
    lon_hi = target_lon + radius_deg

    query = (
        f"{variable}[{time_constraint}]"
        f"[(0.0):1:(0.0)]"
        f"[({lat_lo:.4f}):1:({lat_hi:.4f})]"
        f"[({lon_lo:.4f}):1:({lon_hi:.4f})]"
    )
    return f"{ERDDAP_BASE}{ext}?{query}"


def _fetch_csv(url: str) -> list[dict[str, str]]:
    """Fetch an ERDDAP CSV URL and return rows as list of dicts."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8")

    # ERDDAP .csv has 2 header lines (names, units), then data
    lines = text.strip().split("\n")
    if len(lines) < 3:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return list(reader)


def get_chlorophyll(
    lat: float,
    lon: float,
    date: str | datetime | None = None,
    max_age_days: int = 14,
) -> dict[str, Any] | None:
    """Fetch chlorophyll-a concentration at (lat, lon) from NOAA ERDDAP.

    Tries the most recent data first, then walks back up to 14 days.

    Returns:
        {
            "value": float,            # mg/m^3
            "units": "mg m^-3",
            "lat": float, "lon": float,
            "distance_deg": float,
            "source": "NOAA ERDDAP VIIRS DINEOF",
            "date": str,
            "log10": float,
        }
    or an error dict if all attempts fail.
    """
    last_err = None

    # If explicit date given, only try that one date
    if date is not None:
        dates_to_try = [date]
    else:
        # Otherwise, walk back from today
        dates_to_try = [None] + [
            (datetime.utcnow() - timedelta(days=d)).strftime("%Y-%m-%d")
            for d in range(1, max_age_days)
        ]

    for try_date in dates_to_try:
        url = build_query_url(lat, lon, date=try_date, radius_deg=0.1)
        try:
            rows = _fetch_csv(url)
            if not rows:
                last_err = "empty response"
                continue

            # The CSV has columns: time, altitude, latitude, longitude, chlor_a
            # Each row is one grid cell. Average valid values.
            valid_values = []
            actual_time = None
            for row in rows:
                val_str = row.get("chlor_a") or row.get("chl_oci") or row.get("chlorophyll")
                if not val_str:
                    continue
                try:
                    v = float(val_str)
                except (ValueError, TypeError):
                    continue
                # Skip NaN and fill values
                if math.isnan(v) or v < 0 or v > 1000:
                    continue
                valid_values.append(v)
                if actual_time is None:
                    actual_time = row.get("time", "")

            if not valid_values:
                last_err = "no valid values in response"
                continue

            # Take the cell NEAREST to the requested (lat, lon), not the box mean.
            # Chlorophyll varies 10-100x between coast and offshore, so box
            # averages mix incomparable values. Nearest-cell is the honest answer.
            # The rows also have lat/lon columns we can use for distance.
            # Parse lat/lon from each row, pick the nearest.
            nearest = None
            nearest_dist = float("inf")
            sum_vals = 0.0
            n_vals = 0
            min_v = float("inf")
            max_v = -float("inf")
            for row in rows:
                val_str = row.get("chlor_a") or row.get("chl_oci") or row.get("chlorophyll")
                if not val_str:
                    continue
                try:
                    v = float(val_str)
                except (ValueError, TypeError):
                    continue
                if math.isnan(v) or v < 0 or v > 1000:
                    continue
                sum_vals += v
                n_vals += 1
                min_v = min(min_v, v)
                max_v = max(max_v, v)
                if actual_time is None:
                    actual_time = row.get("time", "")
                # Get cell lat/lon for distance
                try:
                    cell_lat = float(row.get("latitude", 0))
                    cell_lon = float(row.get("longitude", 0))
                except (ValueError, TypeError):
                    continue
                # Equirectangular distance (good enough at 0.1° scale)
                d = math.hypot(cell_lat - lat, cell_lon - lon)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest = v

            if n_vals == 0 or nearest is None:
                last_err = "no valid cells in response"
                continue

            value = nearest
            box_mean = sum_vals / n_vals

            return {
                "value": value,
                "box_mean": box_mean,
                "box_min": min_v,
                "box_max": max_v,
                "n_samples": n_vals,
                "units": "mg m^-3",
                "lat": lat,
                "lon": lon,
                "distance_deg": round(nearest_dist, 4),
                "source": "NOAA ERDDAP VIIRS DINEOF (noaacwNPPN20VIIRSDINEOFDaily)",
                "date": (actual_time or str(try_date) or "latest")[:10],
                "log10": math.log10(value) if value > 0 else None,
                "variable": "chlor_a",
            }
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            continue

    return {
        "error": f"no data in last {max_age_days} days",
        "source": "NOAA ERDDAP VIIRS DINEOF",
        "last_error": last_err,
    }


def get_chlorophyll_with_fallback(
    lat: float,
    lon: float,
    date: str | datetime | None = None,
) -> dict[str, Any] | None:
    """Try NOAA ERDDAP NRT first, then fall back to alternate datasets.

    Returns the first successful result.
    """
    # Try the primary NRT dataset
    result = get_chlorophyll(lat, lon, date)
    if result and "value" in result:
        return result

    # Try alternate ERDDAP datasets as backup
    for name, base_url in ERDDAP_BACKUPS.items():
        for var_name in ("chlor_a", "chl_oci", "chl"):
            time_constraint = "last" if date is None else (
                date.strftime("%Y-%m-%dT12:00:00Z") if isinstance(date, datetime)
                else f"({str(date)}T12:00:00Z):1:({str(date)}T12:00:00Z)"
            )
            url = (
                f"{base_url}.csv?{var_name}[{time_constraint}]"
                f"[(0.0):1:(0.0)]"
                f"[({lat-0.1:.4f}):1:({lat+0.1:.4f})]"
                f"[({lon-0.1:.4f}):1:({lon+0.1:.4f})]"
            )
            try:
                rows = _fetch_csv(url)
                if not rows:
                    continue
                # Pick the cell nearest (lat, lon), don't average the box
                # (coastal blooms + open ocean oligotrophic mix is misleading).
                nearest = None
                nearest_dist = float("inf")
                n_vals = 0
                for row in rows:
                    val_str = row.get(var_name) or row.get("chlor_a")
                    if not val_str:
                        continue
                    try:
                        v = float(val_str)
                    except (ValueError, TypeError):
                        continue
                    if math.isnan(v) or v < 0 or v > 1000:
                        continue
                    n_vals += 1
                    try:
                        cell_lat = float(row.get("latitude", 0))
                        cell_lon = float(row.get("longitude", 0))
                    except (ValueError, TypeError):
                        continue
                    d = math.hypot(cell_lat - lat, cell_lon - lon)
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest = v
                if nearest is None:
                    continue
                return {
                    "value": nearest,
                    "units": "mg m^-3",
                    "lat": lat,
                    "lon": lon,
                    "distance_deg": round(nearest_dist, 4),
                    "source": f"NOAA ERDDAP {name}",
                    "date": rows[0].get("time", "latest")[:10],
                    "log10": math.log10(nearest) if nearest > 0 else None,
                    "n_samples": n_vals,
                }
            except Exception:
                continue

    return {"error": "all ERDDAP datasets failed", "tried": list(ERDDAP_BACKUPS.keys())}
