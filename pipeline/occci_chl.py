"""ESA OC-CCI v6.0 chlorophyll adapter — INDEPENDENT cross-validation.

OC-CCI (Ocean Colour Climate Change Initiative) is the gold-standard
global chlorophyll dataset, produced by Plymouth Marine Laboratory (PML)
on behalf of ESA. It merges SeaWiFS, MODIS-Aqua, MERIS, VIIRS, OLCI-S3A
and OLCI-S3B into a single climate-quality record.

Why add it: the user reported another AI saying our 0.93 mg/m³ value
was wrong. I cross-checked with 3 sources on 2026-08-15 for Chennai
(13.5, 80.5) in the same 0.2° box:

  NOAA VIIRS DINEOF: box mean 0.93   (but 5.14 coastal + 0.28 offshore
                                       averaged — misleading)
  NOAA VIIRS DINEOF: nearest cell 0.28  (open ocean, 0.07° away)
  ESA OC-CCI v6.0:   nearest cell 0.49  (open ocean, ~0.005° away)
  NASA Aqua MODIS:   similar to OC-CCI

The previous ORCA implementation used box-mean, which inflated
coastal blooms with offshore oligotrophic water. The fix in
`erddap_chl.py` takes the nearest cell instead. This new adapter
adds OC-CCI as an independent corroboration.

URL pattern: https://comet.nefsc.noaa.gov/erddap/griddap/occci_v6_daily_1km

Free, no auth, daily, 1 km resolution, 1997-present.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any


ERDDAP_BASE = "https://comet.nefsc.noaa.gov/erddap/griddap/occci_v6_daily_1km"
SOURCE_LABEL = "ESA OC-CCI v6.0 (PML, 1 km, IPCC standard)"


def build_query_url(
    lat: float,
    lon: float,
    date: str | datetime,
    radius_deg: float = 0.05,
    variable: str = "chlor_a",
    ext: str = ".json",
) -> str:
    """Build OC-CCI ERDDAP .json query URL.

    OC-CCI is 2D (no altitude axis), so order is: time, lat, lon.
    """
    if isinstance(date, datetime):
        date_str = date.strftime("%Y-%m-%d")
    else:
        date_str = str(date)
    time_constraint = f"({date_str}T12:00:00Z):1:({date_str}T12:00:00Z)"
    lat_lo, lat_hi = lat - radius_deg, lat + radius_deg
    lon_lo, lon_hi = lon - radius_deg, lon + radius_deg
    query = (
        f"{variable}[{time_constraint}]"
        f"[({lat_lo:.4f}):1:({lat_hi:.4f})]"
        f"[({lon_lo:.4f}):1:({lon_hi:.4f})]"
    )
    return f"{ERDDAP_BASE}{ext}?{query}"


def get_chlorophyll(
    lat: float,
    lon: float,
    date: str | datetime,
    max_age_days: int = 7,
) -> dict[str, Any] | None:
    """Fetch ESA OC-CCI chlorophyll for (lat, lon).

    Strategy change (reliability): query [last] — the server's freshest
    available day — instead of a specific date. Asking for "today" made
    the (US-hosted, India-slow) server answer with HTTP 400 or a read
    timeout on fresh dates that aren't ingested yet; [last] always
    resolves. The true timestamp of the data is read back from the
    response rows and surfaced in `date` — no invented freshness.

    Returns nearest cell (not box mean — chlorophyll is highly
    non-linear spatially, esp. near coasts).
    """
    # Per-day in-process cache: OC-CCI is a climate dataset (changes
    # slowly) but its public ERDDAP can take ~54 s when loaded — repeat
    # clicks for the same point must never pay that twice.
    from pipeline.ttlcache import cached
    return cached(
        f"occci_chl:{lat:.2f},{lon:.2f}",
        43_200,  # 12 h
        lambda: _query_occci(lat, lon),
    )


def _query_occci(lat: float, lon: float) -> dict[str, Any]:
    """Try progressively WIDER boxes until a cloud-free cell is found.

    Ocean-colour satellites cannot see through clouds — during the Indian
    monsoon the tiny 0.05° box around the user's point is often fully
    cloud-masked (all pixels null) even though the server is perfectly
    healthy. Widening to 0.25° then 0.75° usually finds a clear pixel
    nearby; we report the real box used and the cell distance, never a
    fake "at your point" claim.
    """
    last_no_data: dict[str, Any] | None = None
    for radius in (0.05, 0.25, 0.75):
        res = _box_query(lat, lon, radius)
        if res.get("error") and not res.get("error_cloudmask"):
            # Server-side failure (slow/down) — retrying with a BIGGER
            # box only punishes an already-struggling public server.
            return res
        if res.get("value") is not None:
            if radius > 0.05:
                res["note"] = (
                    f"±0.05° box was fully cloud-masked; using nearest clear "
                    f"cell in a ±{radius}° box instead ({res.get('distance_deg')}° away)."
                )
            return res
        last_no_data = res  # answered, but every pixel was null (clouds)
    return last_no_data or {
        "error": "OC-CCI cross-check: no valid values (NOAA primary is used)",
        "source": SOURCE_LABEL,
    }


def _box_query(lat: float, lon: float, radius_deg: float) -> dict[str, Any]:
    """One OC-CCI .json box query. Returns a value dict, a no-value dict
    (cloud-masked box), or an error dict."""
    # Percent-encode the square brackets: Python's urllib sends them RAW
    # (unlike curl), and this server 400s on raw brackets. (Found after
    # a live side-by-side: curl %5B = 200, urllib raw [ = HTTP 400.)
    url = (
        f"{ERDDAP_BASE}.json?chlor_a"
        "%5B(last)%5D"
        f"%5B({lat - radius_deg:.4f}):1:({lat + radius_deg:.4f})%5D"
        f"%5B({lon - radius_deg:.4f}):1:({lon + radius_deg:.4f})%5D"
    )
    try:
        # 22 s: this shared public ERDDAP often needs 20-55 s; the job is
        # capped at 25 s by the parallel gather, so size the socket just
        # under that. Old 8 s cap killed nearly every attempt from India.
        req = urllib.request.Request(url, headers={"User-Agent": "ORCA/1.0"})
        with urllib.request.urlopen(req, timeout=22) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = data.get("table", {}).get("rows", [])
        if not rows:
            return {"error": "OC-CCI cross-check unavailable (empty response — server busy) — NOAA primary is used", "source": SOURCE_LABEL}

        # Find nearest cell with a valid value
        nearest = None
        nearest_dist = float("inf")
        n_vals = 0
        min_v = float("inf")
        max_v = -float("inf")
        actual_time = None
        for row in rows:
            v = row[3]  # chlor_a is column index 3
            if v is None:
                continue
            n_vals += 1
            if actual_time is None:
                actual_time = row[0]
            min_v = min(min_v, v)
            max_v = max(max_v, v)
            cell_lat = row[1]
            cell_lon = row[2]
            d = math.hypot(cell_lat - lat, cell_lon - lon)
            if d < nearest_dist:
                nearest_dist = d
                nearest = v
        if nearest is None:
            # Answered fine — the box is just fully cloud-masked today.
            return {
                "value": None,
                "n_samples": 0,
                "lat": lat,
                "lon": lon,
                "source": SOURCE_LABEL,
                "date": (actual_time or "latest")[:10],
                "error_cloudmask": True,
                "error": (
                    f"OC-CCI: all pixels within ±0.75° are cloud-masked today "
                    f"(monsoon cover — satellites can't see through clouds). "
                    f"NOAA primary is used."[:180]
                ),
            }
        return {
            "value": nearest,
            "box_min": min_v if n_vals else None,
            "box_max": max_v if n_vals else None,
            "n_samples": n_vals,
            "units": "mg m^-3",
            "lat": lat,
            "lon": lon,
            "box_used_deg": radius_deg,
            "distance_deg": round(nearest_dist, 4),
            "source": SOURCE_LABEL,
            "date": (actual_time or "latest")[:10],
            "log10": math.log10(nearest) if nearest > 0 else None,
        }
    except Exception as e:  # noqa: BLE001
        # The comet.nefsc ERDDAP is shared by the whole world and often
        # needs ~54 s — say so plainly instead of a naked TimeoutError.
        why = "server slow" if "timed out" in str(e).lower() or "Timeout" in type(e).__name__ else f"{type(e).__name__}: {e}"
        return {
            "error": f"OC-CCI cross-check unavailable ({why}) — NOAA primary is used"[:180],
            "source": SOURCE_LABEL,
        }
