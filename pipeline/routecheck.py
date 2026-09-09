"""Sea-route legality: is a straight course from A to B water-only?

Why this exists (navigation feature): road-style turn-by-turn routing
DOES NOT EXIST at sea — there is no road graph (OSRM/GraphHopper route
roads, not water). Even real marine chartplotters and the GPS units
Indian fishing boats actually use give a COURSE LINE (rhumb/great-circle)
plus off-course guidance. ORCA does the same, honestly:

  1. The straight leg is sampled every ~2 km against the real GLOBE 1 km
     land mask — if it crosses land (a point off Veraval sailing into the
     Gulf of Khambhat crosses Saurashtra) we SAY so, with the exact spot.
  2. We then try honest detour candidates: perpendicular offsets from the
     first-land point at growing radii, both sides, each re-validated by
     the same mask sampling. First fully-water candidate wins — a REAL
     computed waypoint, not a server lookup and never an invented "safe"
     coordinate.
  3. If nothing clears within the detour budget, we say so plainly
     (peninsulas can need hand piloting around headlands/canals).

Everything is local math on a static real dataset — no network, nothing
pre-baked, and the same answers on a demo laptop with no internet.
"""
from __future__ import annotations

import math

from pipeline import landmask

EARTH_R_KM = 6371.0
SAMPLE_STEP_KM = 2.0
DETOUR_RADII_KM = (10.0, 20.0, 35.0, 55.0, 80.0)
MAX_SAMPLES = 2500  # > that, legs are too long for day-fishing advice anyway


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _lerp(lat1: float, lon1: float, lat2: float, lon2: float, f: float) -> tuple[float, float]:
    """Point f of the way from A to B (linear = rhumb approximation; our
    legs are tens of km so the great-circle difference is < the 1 km
    resolution of the mask — and we SAY which we use)."""
    return lat1 + (lat2 - lat1) * f, lon1 + (lon2 - lon1) * f


def _destination(lat: float, lon: float, bearing: float, dist_km: float) -> tuple[float, float]:
    """Exact spherical destination point (used to place detour candidates)."""
    d = dist_km / EARTH_R_KM
    th = math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(th))
    l2 = l1 + math.atan2(math.sin(th) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return round(math.degrees(p2), 4), round((math.degrees(l2) + 540) % 360 - 180, 4)


def _seg_land_hit(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float, float] | None:
    """First land sample along the leg, as (sail_km_from_start, lat, lon),
    or None when every 2 km sample is water. None (mask says 'unknown')
    counts as water — we never invent an obstruction."""
    dist = _haversine_km(lat1, lon1, lat2, lon2)
    steps = min(MAX_SAMPLES, max(1, int(dist / SAMPLE_STEP_KM)))
    for i in range(1, steps + 1):
        f = i * SAMPLE_STEP_KM / dist if dist else 1.0
        if f > 1.0:
            f = 1.0
        plat, plon = _lerp(lat1, lon1, lat2, lon2, f)
        if landmask.is_land(plat, plon) is True:
            return round(i * SAMPLE_STEP_KM, 1), round(plat, 4), round(plon, 4)
    return None


def compute_sea_route(from_lat: float, from_lon: float,
                      to_lat: float, to_lon: float) -> dict:
    """Result contract (all honest states):

      ok=True,  detour=False → straight leg is water-only
      ok=True,  detour=True  → straight blocked; legs include ONE real
                               computed waypoint that clears land
      ok=False               → blocked, no detour found in budget (reasons given)
      ok=None                → land mask unavailable; leg unchecked
                               (frontend must say 'unverified', not 'safe')
    """
    base = {
        "from": [round(from_lat, 4), round(from_lon, 4)],
        "to": [round(to_lat, 4), round(to_lon, 4)],
        "distance_km": round(_haversine_km(from_lat, from_lon, to_lat, to_lon), 1),
        "distance_nm": round(_haversine_km(from_lat, from_lon, to_lat, to_lon) / 1.852, 1),
        "bearing_deg": round(_bearing_deg(from_lat, from_lon, to_lat, to_lon), 1),
        "sample_step_km": SAMPLE_STEP_KM,
        "method": "rhumb-line sampling vs GLOBE 1 km land mask (local, real)",
    }
    if not landmask.enabled():
        return {**base, "ok": None,
                "reason": "land mask unavailable — course NOT verified",
                "legs": [base["from"], base["to"]], "detour": False}

    try:
        hit = _seg_land_hit(from_lat, from_lon, to_lat, to_lon)
    except Exception:  # noqa: BLE001
        return {**base, "ok": None,
                "reason": "land check errored — course NOT verified",
                "legs": [base["from"], base["to"]], "detour": False}

    if hit is None:
        return {**base, "ok": True, "detour": False,
                "legs": [base["from"], base["to"]],
                "reason": "straight course: water all the way"}

    sail_km, hit_lat, hit_lon = hit
    brg = base["bearing_deg"]
    # Detour candidates: radial offsets around the FIRST-land point.
    # Lateral (±90°) first — shortest honest bypass; then increasingly
    # wrapped angles so a peninsula can be rounded via its seaward cape
    # (offsets pointing back at the coast die fast on the land probe).
    angle_order = (90, -90, 60, -60, 120, -120, 30, -30,
                   150, -150, 0, 180, 45, -45, 135, -135)
    for radius in DETOUR_RADII_KM:
        for da in angle_order:
            cand_lat, cand_lon = _destination(hit_lat, hit_lon, brg + da, radius)
            if landmask.is_land(cand_lat, cand_lon) is True:
                continue
            try:
                if (_seg_land_hit(from_lat, from_lon, cand_lat, cand_lon) is None
                        and _seg_land_hit(cand_lat, cand_lon, to_lat, to_lon) is None):
                    leg1 = _haversine_km(from_lat, from_lon, cand_lat, cand_lon)
                    leg2 = _haversine_km(cand_lat, cand_lon, to_lat, to_lon)
                    return {**base, "ok": True, "detour": True,
                            "legs": [base["from"], [cand_lat, cand_lon], base["to"]],
                            "distance_km": round(leg1 + leg2, 1),
                            "distance_nm": round((leg1 + leg2) / 1.852, 1),
                            "land_hit": {"lat": hit_lat, "lon": hit_lon, "sail_km": sail_km},
                            "reason": (f"direct course crosses land {sail_km:.0f} km out "
                                       f"— detour waypoint computed {radius:.0f} km clear of it") }
            except Exception:  # noqa: BLE001
                continue

    return {**base, "ok": False, "detour": False,
            "legs": [base["from"], base["to"]],
            "land_hit": {"lat": hit_lat, "lon": hit_lon, "sail_km": sail_km},
            "reason": (f"course crosses land {sail_km:.0f} km out and no sea-only "
                       f"detour cleared within {DETOUR_RADII_KM[-1]:.0f} km — treat as "
                       "blocked; sail around the coast manually (we never draw a "
                       "fake safe line)")}
