"""Land/sea mask built from REAL elevation data (GLOBE 1 km, via the
global-land-mask package).

Why this exists: NOAA's DINEOF chlorophyll grid (our primary chl source)
occasionally reports values ON LAND — coastal bleed / sediment pixels and
inland water bodies (e.g. Chilika lagoon reads ~7 mg/m³, and stray
farmland pixels near Ganjam read ~5.6 mg/m³ in the same pass that fed
the 2026-09-08 demo screenshots). Ranking those as "fishing hotspots"
points fishermen at dry ground — a real bug caught in review.

The mask is a real, static, public dataset (GLOBE global 1 km elevation,
land = elevation > 0). It is not an approximation we invented and it
needs no network at runtime, so it works the same on a demo laptop with
flaky wi-fi.

Honest degradation: if the optional package is missing or errors,
is_land() returns None ("unknown") and callers MUST treat None as KEEP —
we never throw data away just because the mask is unavailable.

Note: large inland water bodies (lagoons/lakes, e.g. Chilika) count as
land here on purpose — their plankton is real but they are not offshore
fishing targets, and INCOIS PFZ-style advice is for the open sea.
"""
from __future__ import annotations

_globe = None
try:  # optional dependency — never let import failure crash the pipeline
    from global_land_mask import globe as _globe  # type: ignore
except Exception:  # noqa: BLE001
    _globe = None

_ENABLED = _globe is not None


def enabled() -> bool:
    """True when the real GLOBE 1 km mask is loaded and usable."""
    return _ENABLED


def is_land(lat: float, lon: float) -> bool | None:
    """True = land, False = sea, None = unknown (mask unavailable/error).

    Callers: treat None as "no information" — keep the data point.
    """
    if _globe is None:
        return None
    try:
        return bool(_globe.is_land(lat, lon))
    except Exception:  # noqa: BLE001
        return None
