"""Voyage Planner — "TU analyze kar ke bata: kahan jaun?"

Candidate destinations come only from official INCOIS PFZ advisory-line
geometry. Generic chlorophyll cells are not converted into fishing
recommendations: ORCA has no validated species/season/catch model.

Each candidate is checked against the point marine forecast using the shared
route-advisory thresholds. The numeric ``score`` is an explicitly experimental,
auditable ordering of official PFZ candidates by weather-evidence state,
distance, and optional crowd-spreading signals. It is not an INCOIS score,
probability of catch, safety certification, or scientific PFZ model.

No official PFZ geometry means ``found:false`` with the provider failure/no-data
reason. Unknown weather remains unknown and is penalized in ranking rather than
being treated as safe.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from pipeline import forecast as fc

MAX_CANDIDATES = 8
TOP_N = 5
# Compatibility constants used by older clients/tests. All candidates are now
# official PFZ points, so no source/chlorophyll bonus is applied.
PFZ_BONUS = 0
BLOOM_BONUS = 0
UNKNOWN_WEATHER_PENALTY = 60
PER_POINT_TIMEOUT_SEC = 35

# B14 crowd-spread: GFW fleet pressure is deep-checked only on the
# current top-3 (quota-friendly), community load on every candidate.
SPREAD_GFW_TOP = 3
GFW_RADIUS_DEG = 0.5          # ~50 km half-width pressure box
GFW_LOOKBACK_DAYS = 30
GFW_TIMEOUT_SEC = 20
# B15: burst-pause resilience — crowd pressure is remembered per 0.5°
# cell; when GFW's burst limiter pauses fresh fetches, the last-good
# hours (≤6 h old) are served WITH an honest age label instead of
# failing the whole fleet signal.
CROWD_GFW_STALE_MAX_AGE_SEC = 6 * 3600


# ── pure scoring (test-pinned, network-free) ───────────────────────

def _score(state: str, kind: str, chl: float | None, dist_nm: float) -> int:
    """Experimental official-PFZ ordering score; never a catch probability."""
    del kind, chl  # retained in the internal signature for compatibility
    score = 100
    if state == "danger":
        score -= 80
    elif state == "unknown":
        score -= UNKNOWN_WEATHER_PENALTY
    elif state == "caution":
        score -= 40
    score -= int(dist_nm * 0.15 + 0.5)
    return max(0, score)


def _reasons(state_row: dict[str, Any], kind: str, chl: float | None,
             dist_nm: float, pfz_meta: dict[str, Any] | None) -> list[str]:
    """Human-readable audit of the score — every delta named. Pure."""
    out: list[str] = []
    st = state_row.get("state")
    w = state_row.get("wave_m")
    if kind == "pfz" and pfz_meta:
        out.append(
            f"official INCOIS PFZ advisory ({pfz_meta.get('advisory_date')}); "
            f"sector {pfz_meta.get('sector_name')} — eligibility only, +0"
        )
    # Chlorophyll is deliberately ignored: generic high-chlorophyll pixels do
    # not establish PFZ/catch suitability. ``chl`` remains a compatibility arg.
    del chl
    if st == "danger":
        out.append(f"⚠ {state_row.get('why') or 'dangerous sea state'} −80")
    elif st == "unknown":
        out.append(f"weather evidence incomplete −{UNKNOWN_WEATHER_PENALTY} (not scored safe)")
    elif st == "caution":
        out.append(f"⚠ {state_row.get('why') or 'rough for small craft'} −40")
    elif w is not None:
        out.append(f"configured thresholds not crossed; wave {w:.1f} m ±0")
    out.append(f"{dist_nm:.0f} NM away −{int(dist_nm * 0.15 + 0.5)}")
    return out


def _point_state_stub(pf: dict[str, Any] | None) -> dict[str, Any]:
    """Reuse the transit verdict point logic (single source of truth)."""
    from pipeline.routeadvisory import _point_state
    state, row = _point_state(pf)
    return {"state": state, **row}


# ── candidate generation (REAL sources) ────────────────────────────

def _pfz_candidates(lat: float, lon: float, max_km: float,
                    notes: list[str]) -> list[dict[str, Any]]:
    from pipeline import incois_pfz
    try:
        data = incois_pfz.get_lines()
        lines = data.get("lines") or []
    except Exception as e:  # noqa: BLE001
        notes.append(f"INCOIS PFZ fetch failed: {type(e).__name__}: {e}")
        return []
    ad_date = data.get("advisory_date")
    cands: list[dict[str, Any]] = []
    for ln in lines:
        coords = ln.get("coords") or []  # [[lon, lat], ...] (GeoJSON order)
        if len(coords) < 2:
            continue
        try:
            # returns (dist_km, (lat, lon)) — REAL nearest point on the line
            d_km, (nlat, nlon) = incois_pfz.distance_to_polyline_km(lat, lon, coords)
        except Exception:  # noqa: BLE001
            continue
        if d_km is None or d_km > max_km:
            continue
        cands.append({
            "lat": round(nlat, 4), "lon": round(nlon, 4),
            "kind": "pfz",
            "name": f"PFZ · {ln.get('sector_name') or 'coast'}",
            "pfz_meta": {
                "advisory_date": ad_date,
                "sector_name": ln.get("sector_name"),
                "line_length_km": ln.get("length_km"),
            },
            "chl": None,
            "dist_km": d_km,
        })
    cands.sort(key=lambda c: c["dist_km"])
    seen, uniq = set(), []
    for c in cands:  # same-side lines dedup (0.05° grid)
        k = (round(c["lat"], 2), round(c["lon"], 2))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


# ── B14 crowd-spread ───────────────────────────────────────────────

def _gfw_cell_key(lat: float, lon: float) -> str:
    """0.5° crowd-pressure cell — one remembered value serves the area."""
    return f"crowd:gfwcell:{round(lat * 2) / 2:.1f},{round(lon * 2) / 2:.1f}"


def _gfw_pressure(lat: float, lon: float) -> dict[str, Any] | None:
    """GFW apparent-fishing activity used as a crowd-ranking heuristic.

    End date is shifted back 3 days — GFW's processing pipeline lags
    real time by ~3 days, and _clamp_date_range snaps to dataset range.

    B15: every success is remembered as the cell's last-good (6 h);
    a burst-429 / network failure then serves that labelled copy
    instead of collapsing the whole fleet signal.
    """
    from datetime import date, timedelta
    from pipeline import gfw, ttlcache
    end = date.today() - timedelta(days=3)
    start = end - timedelta(days=GFW_LOOKBACK_DAYS - 1)
    res = gfw.get_fishing_effort(lat, lon, start.isoformat(),
                                 end.isoformat(), radius_deg=GFW_RADIUS_DEG)
    key = _gfw_cell_key(lat, lon)
    if isinstance(res, dict) and res.get("hours") is not None and "error" not in res:
        try:
            ttlcache.remember_last_good(key, res)
        except Exception:  # noqa: BLE001 — remember karna optional hai
            pass
        return res
    try:
        stale = ttlcache.get_last_good(key, CROWD_GFW_STALE_MAX_AGE_SEC)
    except Exception:  # noqa: BLE001
        stale = None
    if isinstance(stale, dict) and stale.get("hours") is not None:
        return stale  # carries _stale / _stale_age_sec honesty labels
    return res


def _spread(recs: list[dict[str, Any]], notes: list[str]) -> None:
    """Crowd-aware re-ranking — "sabko same jagah mat bhejo".

    Stage 1 (free, every candidate): OUR OWN community load — how many
    ORCA fishers were already sent near this cell in the last 24 h.
    Stage 2 (quota-friendly, top-3 only): GFW AIS fleet hours nearby.

    Both deductions are appended to reasons[] with exact numbers, then
    recs are re-sorted. The served #1 is recorded anonymously so the
    NEXT fisher is naturally nudged towards the next-best spot —
    self-balancing without any user accounts or tracking.
    """
    from pipeline import crowd
    now = time.time()

    # stage 1 — community signal on every candidate (local, instant)
    for r in recs:
        info = crowd.load(r["lat"], r["lon"], now)
        pen = crowd.community_penalty(info["effective"])
        r["crowd"] = {
            "level": crowd.level(info["effective"]),
            "community_recent": info["same_cell"],
            "community_load": info["effective"],
            "community_penalty": pen,
            "gfw_hours_30d": None,
            "gfw_penalty": 0,
            "note": None,
        }
        if pen > 0:
            r["reasons"].append(
                f"👥 {info['same_cell']} ORCA fisher(s) already sent here "
                f"in 24 h (load {info['effective']:.1f}) −{pen} — spreading"
            )

    prelim = sorted(recs, key=lambda r: -(r["score"] - r["crowd"]["community_penalty"]))
    deep = prelim[:SPREAD_GFW_TOP]

    # stage 2 — GFW fleet pressure on the current leaders (parallel)
    gfw_fail = 0
    gfw_reason = ""

    # B15: burst-pause precheck — if GFW already told us to wait, DO NOT
    # fire any HTTP at all; only the remembered cell pressure may answer.
    # (One active HTTP 429 window must not be hit by three fresh calls.)
    try:
        from pipeline import gfw as _gfw_mod
        _paused = float(_gfw_mod._rate_limit_remaining())
    except Exception:  # noqa: BLE001
        _paused = 0.0

    def grab(idx: int, r: dict[str, Any]) -> None:
        try:
            if _paused > 0:
                from pipeline import ttlcache as _tc
                stale = _tc.get_last_good(_gfw_cell_key(r["lat"], r["lon"]),
                                          CROWD_GFW_STALE_MAX_AGE_SEC)
                gfwres[idx] = stale if isinstance(stale, dict) else {
                    "error": (f"GFW burst-pause active (~{int(_paused)}s left), "
                              "no remembered fleet pressure for this cell yet")}
            else:
                gfwres[idx] = _gfw_pressure(r["lat"], r["lon"])
        except Exception as e:  # noqa: BLE001
            gfwres[idx] = {"error": f"{type(e).__name__}: {e}"}

    gfwres: dict[int, Any] = {}
    ex = ThreadPoolExecutor(max_workers=max(1, min(3, len(deep))))
    try:
        futs = {ex.submit(grab, i, r): i for i, r in enumerate(deep)}
        for fut in as_completed(futs):
            try:
                fut.result(timeout=GFW_TIMEOUT_SEC)
            except Exception as e:  # noqa: BLE001
                gfwres[futs[fut]] = {"error": f"{type(e).__name__}: {e}"}
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    for i, r in enumerate(deep):
        res = gfwres.get(i)
        hours = res.get("hours") if isinstance(res, dict) else None
        if hours is None:
            gfw_fail += 1
            err = (res or {}).get("error", "no response") if isinstance(res, dict) else "no response"
            r["crowd"]["note"] = (f"GFW fleet check unavailable ({err}) — community "
                                  "signal only, no fleet penalty added (+0)")
            if not gfw_reason:
                gfw_reason = str(err)
            continue
        press = crowd.gfw_pressure(hours)
        r["crowd"]["gfw_hours_30d"] = round(hours, 1)
        r["crowd"]["gfw_penalty"] = press["penalty"]
        r["crowd"]["level"] = crowd.worst_level(r["crowd"]["level"], press["level"])
        if isinstance(res, dict) and res.get("_stale"):
            age_min = int((res.get("_stale_age_sec") or 0) // 60)
            r["crowd"]["note"] = (f"GFW hours last-good cache se ({age_min} min purane) — "
                                  "burst-pause mein bhi fleet signal mila, honestly labelled")
        if press["penalty"] > 0:
            r["reasons"].append(
                f"🚢 GFW AIS: {hours:.1f} apparent-fishing hrs in the query area/30 d "
                f"(experimental crowd penalty) −{press['penalty']}")
        else:
            r["reasons"].append(
                f"🚢 GFW AIS: {hours:.1f} apparent-fishing hrs in the query area/30 d — no crowd penalty ±0")

    if gfw_fail:
        notes.append(f"GFW fleet-pressure check failed for {gfw_fail} spot(s) "
                     f"({gfw_reason}) — ranked on community + weather signals only")

    # final auditable re-rank: score_base − community − fleet pressure
    for r in recs:
        r["score_base"] = r["score"]
        r["score"] = max(0, r["score_base"]
                         - r["crowd"]["community_penalty"]
                         - r["crowd"]["gfw_penalty"])
    recs.sort(key=lambda r: -r["score"])

    if recs:
        crowd.record(recs[0]["lat"], recs[0]["lon"], kind=recs[0].get("kind", "hotspot"))
        if all(r["crowd"]["level"] == "high" for r in recs):
            notes.append("all near spots are high-pressure right now — showing "
                         "best available; kal naya PFZ advisory aayega")


# ── main entry ─────────────────────────────────────────────────────

def recommend(lat: float, lon: float, max_km: float = 120.0) -> dict[str, Any]:
    notes: list[str] = []
    cands = _pfz_candidates(lat, lon, max_km, notes)
    # Every candidate must originate in official INCOIS PFZ geometry.
    seen, pool = set(), []
    for c in sorted(cands, key=lambda c: (c["kind"] != "pfz", c["dist_km"] or 1e9)):
        k = (round(c["lat"], 1), round(c["lon"], 1))
        if k in seen or len(pool) >= MAX_CANDIDATES:
            continue
        seen.add(k)
        pool.append(c)

    if not pool:
        return {
            "found": False,
            "from": [round(lat, 4), round(lon, 4)],
            "recommendations": [],
            "notes": notes + ["no official INCOIS PFZ candidate within max_km "
                              f"{max_km:.0f} km"],
            "ranking_status": "unavailable_without_official_pfz",
            "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    # safety gate: live forecast per candidate (parallel, shared cache)
    weath: dict[int, Any] = {}
    wfail: dict[int, str] = {}

    def one(i: int, c: dict[str, Any]):
        try:
            weath[i] = fc.get_point_forecast(c["lat"], c["lon"])
        except Exception as e:  # noqa: BLE001
            wfail[i] = f"{type(e).__name__}: {e}"

    ex = ThreadPoolExecutor(max_workers=min(5, len(pool)))
    try:
        futs = {ex.submit(one, i, c): i for i, c in enumerate(pool)}
        for fut in as_completed(futs):
            try:
                fut.result(timeout=PER_POINT_TIMEOUT_SEC)
            except Exception as e:  # noqa: BLE001
                i = futs[fut]
                if i not in wfail:
                    wfail[i] = f"{type(e).__name__}: {e}"
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    recs: list[dict[str, Any]] = []
    from pipeline.routecheck import _bearing_deg
    for i, c in enumerate(pool):
        row = _point_state_stub(weath.get(i))
        dist_nm = (c["dist_km"] or 0) / 1.852
        score = _score(row["state"], c["kind"], c["chl"], dist_nm)
        cands_reasons = _reasons(row, c["kind"], c["chl"], dist_nm, c["pfz_meta"])
        if i in wfail:
            notes.append(f"weather gate failed for {c['name']}: {wfail[i]}")
            cands_reasons = ["weather unknown (honest unknown — not scored safe)"] + cands_reasons
        recs.append({
            **{k: c[k] for k in ("lat", "lon", "kind", "name", "chl")},
            "distance_nm": round(dist_nm, 1),
            "bearing_deg": _bearing_deg(lat, lon, c["lat"], c["lon"]),
            "state": row["state"] if i not in wfail else "unknown",
            "wave_m": row.get("wave_m"),
            "wind_kn": row.get("wind_kn"),
            "sst_c": row.get("sst_c"),
            "why": row.get("why") or row.get("note"),
            "score": score,
            "reasons": cands_reasons,
        })
    recs.sort(key=lambda r: -r["score"])
    _spread(recs, notes)

    return {
        "found": True,
        "from": [round(lat, 4), round(lon, 4)],
        "max_km": max_km,
        "recommendations": recs[:TOP_N],
        "candidates_evaluated": len(pool),
        "spreading": True,
        "notes": notes,
        "ranking_status": "experimental_non_authoritative",
        "ranking_disclaimer": (
            "Orders official INCOIS PFZ candidates only. Score is not from INCOIS, "
            "not a catch probability, and not a safety certification."
        ),
        "sources": {
            "pfz": "INCOIS PFZ Advisory (GeoServer WFS)",
            "weather": "Open-Meteo Marine + Forecast (per-candidate threshold check)",
            "fleet": "Global Fishing Watch AIS apparent-fishing effort (top-3 crowd context)",
            "community": "ORCA anonymous 24 h served-pick cells (0.25°)",
        },
        "scoring": (
            f"experimental ordering: 100 base −80 danger −40 caution "
            f"−{UNKNOWN_WEATHER_PENALTY} unknown weather −0.15/NM distance "
            "−0-24 community-spread −0-10 GFW activity pressure; official PFZ "
            "geometry is an eligibility gate, not a bonus"
        ),
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
