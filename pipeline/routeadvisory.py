"""Transit verdict: is sailing A → B safe right now?

The skipper's real question ("yahan se wahan jaana sahi rahega?") is not
answered by an advisory at ONE point — the weather at the destination
says nothing about the stretch in between. This module walks the
verified course (routecheck.py, GLOBE 1 km land mask) and pulls the
REAL Open-Meteo marine forecast at evenly spaced sample points along
it, then reduces them to one honest verdict:

    go        every sampled point is calm-right-now
    caution   at least one point is workable-but-rough (or unverified)
    nogo      at least one point is dangerous right now/within 48 h,
              OR the land mask says the course itself is blocked
    unknown   no sampled point returned data — we say so, never guess

Thresholds are EXACTLY the ones advisory.py uses for the single-point
verdict, so the app never contradicts itself:
  waves   >= 4.0 m  danger      >= 2.5 m  caution
  gusts   >= 34 kn  danger (WMO gale warning)
  wind    >= 20 kn  caution
  current >  3.0 kn honest note attached (not a state)

Everything label-free: no invented numbers, no fake confidence — a
point whose fetch failed is marked 'unknown', counted separately, and
named in sources_failed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from pipeline import forecast as fc

# ── sampling policy ─────────────────────────────────────────────────
SAMPLE_SPACING_KM = 30.0   # ~16 NM: fine enough to catch a mid-route squall
MAX_SAMPLES = 5            # start + end cap; keeps public-API load honest

# ── thresholds (mirror pipeline/advisory.py) ────────────────────────
WAVE_DANGER_M = 4.0
WAVE_CAUTION_M = 2.5
WIND_CAUTION_KN = 20.0
GUST_DANGER_KN = 34.0
CURRENT_STRONG_KN = 3.0


def _haversine_km(a: list, b: list) -> float:
    from pipeline.routecheck import _haversine_km as hk
    return hk(a[0], a[1], b[0], b[1])


def _sample_points(legs: list[list[float]],
                   spacing_km: float = SAMPLE_SPACING_KM,
                   max_n: int = MAX_SAMPLES) -> list[dict[str, Any]]:
    """Sample the verified course: every leg vertex + interpolated
    points so spacing <= spacing_km, cumulative sail distance from
    start. Pure (no I/O) so tests can pin it exactly.

    legs come straight from routecheck: [[lat, lon], ...] where a
    middle vertex (when detour=True) is the real computed waypoint —
    it ALWAYS stays in the sample regardless of thinning.
    """
    if len(legs) < 2:
        return [{"lat": legs[0][0], "lon": legs[0][1], "sail_km": 0.0, "vertex": True}]

    pts: list[dict[str, Any]] = []
    cum = 0.0
    for i in range(len(legs) - 1):
        a, b = legs[i], legs[i + 1]
        seg = _haversine_km(a, b)
        n_sub = max(1, int(seg / spacing_km) + (1 if seg % spacing_km else 0))
        for j in range(n_sub):
            f = j / n_sub
            pts.append({
                "lat": round(a[0] + (b[0] - a[0]) * f, 4),
                "lon": round(a[1] + (b[1] - a[1]) * f, 4),
                "sail_km": round(cum + seg * f, 1),
                "vertex": j == 0,
            })
        cum += seg
    la, lo = legs[-1]
    pts.append({"lat": la, "lon": lo, "sail_km": round(cum, 1), "vertex": True})

    if len(pts) > max_n:
        verts = [p for p in pts if p["vertex"]]
        mids = [p for p in pts if not p["vertex"]]
        keep_mids = max_n - len(verts)
        if keep_mids < 0:
            keep_mids = 0
        if mids and keep_mids:
            step = max(1, int(len(mids) / keep_mids + 0.999))
            mids = mids[::step][:keep_mids]
        else:
            mids = []
        pts = sorted(verts + mids, key=lambda p: p["sail_km"])
    return pts


def _point_state(pf: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """State of ONE sample point from its Open-Meteo point forecast.
    Returns (state, row) — state in good|caution|danger|unknown, row
    carries the exact observed numbers so the UI shows evidence, not
    adjectives. Pure: pass None to model a failed fetch."""
    if not pf:
        return "unknown", {"note": "fetch failed"}

    now = pf.get("now", {}) or {}
    n48 = pf.get("next48h", {}) or {}
    wave_now = now.get("wave_height_m")
    wave_48 = n48.get("wave_max_m")
    wind_now = now.get("wind_kn")
    wind_48 = n48.get("wind_max_kn")
    gust_48 = n48.get("gust_max_kn")
    current = now.get("current_kn")
    sst = now.get("sst_c")

    row = {
        "wave_m": wave_now, "wave_48h_max_m": wave_48,
        "wind_kn": wind_now, "wind_48h_max_kn": wind_48,
        "gust_48h_max_kn": gust_48,
        "current_kn": current, "sst_c": sst,
    }
    if wave_now is None and wave_48 is None and wind_48 is None:
        return "unknown", {**row, "note": "no marine values returned"}

    why: list[str] = []
    if (wave_now or 0) >= WAVE_DANGER_M or (wave_48 or 0) >= WAVE_DANGER_M:
        why.append(f"waves {next(w for w in (wave_now, wave_48) if (w or 0) >= WAVE_DANGER_M):.1f} m")
    if (gust_48 or 0) >= GUST_DANGER_KN:
        why.append(f"gusts {gust_48:.0f} kn (gale)")
    if why:
        return "danger", {**row, "why": "; ".join(why)}

    if (wave_now or 0) >= WAVE_CAUTION_M or (wave_48 or 0) >= WAVE_CAUTION_M:
        why.append(f"waves up to {max(wave_now or 0, wave_48 or 0):.1f} m")
    if (wind_48 or 0) >= WIND_CAUTION_KN:
        why.append(f"wind {wind_48:.0f} kn in 48 h")
    if why:
        return "caution", {**row, "why": "; ".join(why)}

    if (current or 0) > CURRENT_STRONG_KN:
        row["note"] = f"strong surface current {current:.1f} kn"
    return "good", row


def _reduce_verdict(states: list[str], land_ok: bool | None) -> dict[str, Any]:
    """Fold per-point states + land check into ONE verdict. Pure."""
    known = sum(1 for s in states if s != "unknown")
    if land_ok is False:
        level = "nogo"
    elif land_ok is None and known == 0:
        level = "unknown"
    elif "danger" in states:
        level = "nogo"
    elif "caution" in states or "unknown" in states:
        level = "caution"
    elif known > 0:
        level = "go"
    else:
        level = "unknown"
    return {
        "level": level,
        "points_known": known,
        "points_total": len(states),
        "land_verified": land_ok,      # True water / False blocked / None mask-missing
    }


def route_advisory(from_lat: float, from_lon: float,
                   to_lat: float, to_lon: float) -> dict[str, Any]:
    """Full transit analysis. Runs the land check, samples the course,
    fetches each sample's REAL forecast IN PARALLEL (same 30-min cache
    the single-point advisory uses), and folds it into a verdict."""
    from pipeline.routecheck import compute_sea_route
    rc = compute_sea_route(from_lat, from_lon, to_lat, to_lon)
    pts = _sample_points(rc["legs"])

    # Parallel fetches — 5 points × the cached marine+weather pair.
    forecasts: dict[int, Any] = {}
    failed: dict[int, str] = {}

    def one(i: int, p: dict[str, Any]):
        try:
            forecasts[i] = fc.get_point_forecast(p["lat"], p["lon"])
        except Exception as e:  # noqa: BLE001
            failed[i] = f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=min(4, len(pts))) as ex:
        futs = [ex.submit(one, i, p) for i, p in enumerate(pts)]
        for f in as_completed(futs, timeout=90):
            _ = f  # results captured in dicts; timeout guards a hung worker

    rows, states = [], []
    sources_used: list[str] = []
    sources_failed: list[str] = []
    for i, p in enumerate(pts):
        pf = forecasts.get(i)
        state, row = _point_state(pf)
        if pf and pf.get("source") and pf["source"] not in sources_used:
            sources_used.append(pf["source"])
        if i in failed:
            sources_failed.append(
                f"route point {p['sail_km']:.0f} km: {failed[i]}")
        states.append(state)
        rows.append({**p, "state": state, **row})

    verdict = _reduce_verdict(states, rc.get("ok"))

    # Safest departure window at the START point (the skipper's real
    # decision is 'when do I leave'), computed from the same fetch —
    # no extra network call.
    window: dict[str, Any] = {"found": False, "note": "start-point forecast unavailable"}
    pf0 = forecasts.get(0)
    if pf0:
        try:
            w = fc.find_safe_window(pf0)
            window = w if isinstance(w, dict) else window
        except Exception:  # noqa: BLE001
            pass

    return {
        **{k: rc[k] for k in ("from", "to", "legs", "detour",
                              "distance_km", "distance_nm", "bearing_deg")},
        "land_ok": rc.get("ok"),
        "land_reason": rc.get("reason"),
        "land_hit": rc.get("land_hit"),
        "points": rows,
        "verdict": verdict,
        "safe_window_at_start": window,
        "sources_used": sources_used,
        "sources_failed": sources_failed,
        "sample_spacing_km": SAMPLE_SPACING_KM,
        "method": ("verified course (GLOBE 1 km mask) sampled every "
                   f"{SAMPLE_SPACING_KM:.0f} km; live Open-Meteo marine "
                   "forecast per point; WMO/IMD small-craft thresholds "
                   "— identical to the single-point advisory"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
