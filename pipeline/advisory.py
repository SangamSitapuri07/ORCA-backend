"""Deterministic safety advisory — the "Can I go out today?" card.

NO LLM. Every number comes from a live data source, every rule is a
published small-craft threshold, every verdict traceable to its reason.

Data woven together for one lat/lon:
  1. zone_snapshot        (SST, chlorophyll — existing ORCA pipeline)
  2. point forecast       (waves / wind / gusts / rain, next 72 h)
  3. INCOIS official PFZ  (nearest advisory line, distance + bearing)
  4. JTWC cyclones        (active tropical systems, distance)

Verdicts:
  go       → no reason at caution level or higher
  caution  → at least one caution-level reason, no no-go reason
  no_go    → at least one no-go reason

Rules (small-craft practice, WMO/IMD conventions):
  no_go    active cyclone within 300 km, or gale-force gusts ≥ 34 kn
           (WMO gale warning), or waves ≥ 4 m, or ≥ 64.5 mm rain day
           (IMD "heavy rain" threshold)
  caution  cyclone 300–800 km, winds 20–34 kn, gusts 28–34 kn,
           waves 2.5–4 m, swell ≥ 2.5 m, rain 35–64.5 mm day
  info     bloom-level chlorophyll (> 8 mg/m³) health note; PFZ context
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pipeline import forecast as fc
from pipeline import incois_pfz, jtwc
from pipeline.orca_data import zone_snapshot_cached

# Validity of one advisory — ocean forecasts stale fast; re-issue after this.
ADVISORY_TTL_HOURS = 3


def _deg_to_compass(deg: float | None) -> str | None:
    if deg is None:
        return None
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) // 22.5) % 16]


def build_advisory(
    lat: float,
    lon: float,
    target_date: str | None = None,
    include_gfw: bool = False,
) -> dict[str, Any]:
    """Compose the full advisory card for one point.

    include_gfw=False by default: GFW takes 30+ s and isn't needed for a
    safety verdict. The chat PFZ flow can flip it on ("deep mode").
    """
    started = datetime.now(timezone.utc)
    sources_used: list[str] = []
    sources_failed: list[str] = []
    reasons: list[dict[str, Any]] = []

    def reason(severity: str, code: str, msg: str):
        reasons.append({"severity": severity, "code": code, "msg": msg})

    # ── 1. Snapshot (SST + chlorophyll; GFW off in fast mode) ──
    snap: dict[str, Any] = {}
    try:
        snap = zone_snapshot_cached(lat, lon, target_date, include_gfw=include_gfw)
        sources_used += snap.get("data_sources_used", [])
        sources_failed += snap.get("data_sources_failed", [])
    except Exception as e:  # noqa: BLE001
        sources_failed.append(f"zone snapshot: {type(e).__name__}: {e}")

    # ── 2. Hourly forecast + safe window ──
    try:
        point_fc = fc.get_point_forecast(lat, lon)
        sources_used.append(point_fc["source"])
        safe_window = fc.find_safe_window(point_fc)
    except Exception as e:  # noqa: BLE001
        point_fc = {}
        safe_window = {"found": False, "note": "Forecast fetch failed."}
        sources_failed.append(f"point forecast: {type(e).__name__}: {e}")

    now_f = point_fc.get("now", {}) or {}
    n24 = point_fc.get("next24h", {}) or {}
    n48 = point_fc.get("next48h", {}) or {}
    # Sparkline view of the SAME arrays the rules below read — the chart
    # the user sees is literally the evidence the verdict was built from.
    hourly_chart = fc.chart_series(point_fc) if point_fc else None

    wave_now = now_f.get("wave_height_m")
    swell_now = now_f.get("swell_height_m")
    wind_now = now_f.get("wind_kn")
    gust_now = now_f.get("gust_kn")
    current_kn = now_f.get("current_kn")
    # SST: first the daily point record (ZoneSnapshot); if that source is
    # down, fall back to the hourly marine-model SST the SAME forecast
    # fetch already returned — honestly labelled by source.
    snap_sst = snap.get("sst_mean") if snap.get("sst_mean") is not None else snap.get("sst_max")
    if snap_sst is not None:
        sst_c = snap_sst
        sst_source = "Open-Meteo daily SST record (point)"
    elif now_f.get("sst_c") is not None:
        sst_c = now_f.get("sst_c")
        sst_source = "Open-Meteo marine model (hourly forecast SST)"
    else:
        sst_c = None
        sst_source = None
    chl = snap.get("chlorophyll")

    # ── 3. Cyclones (JTWC) ──
    cyclone_dist_km: float | None = None
    cyclone_note = "Cyclone status not checked."
    try:
        # Basin-filtered like alerts.evaluate — ORCA serves Indian
        # waters; a far-away WPac typhoon must never tint the verdict.
        cyc = jtwc.nearest_cyclone(lat, lon, basins=["io", "sh"])
        if cyc.get("found"):
            c = cyc["cyclone"]
            cyclone_dist_km = cyc["distance_km"]
            nm = round(cyclone_dist_km / 1.852)
            label = c.get("name") or c["designation"]
            inten = c.get("intensity") or "tropical system"
            wind = f"{c['max_wind_kt']} kn" if c.get("max_wind_kt") else "? kn"
            cyclone_note = (
                f"Active {inten} '{label}' {nm} NM away "
                f"({_deg_to_compass(cyc['bearing_deg'])}), winds {wind}."
            )
            if cyclone_dist_km < 300:
                reason("no_go", "cyclone_near", f"🌀 {cyclone_note}")
            elif cyclone_dist_km < 800:
                reason("caution", "cyclone_region", f"🌀 {cyclone_note}")
            else:
                reason("info", "cyclone_far", f"🌀 {cyclone_note}")
        else:
            cyclone_note = cyc.get("note", "No active tropical cyclone in the region.")
            if cyc.get("checked"):
                reason("info", "no_cyclone", f"✅ {cyclone_note}")
            else:
                reason("info", "cyclone_check_failed", f"⚠️ {cyclone_note}")
    except Exception as e:  # noqa: BLE001
        cyclone_note = f"Cyclone check failed: {type(e).__name__}"
        reason("info", "cyclone_check_failed", "Could not verify cyclone status — check IMD before departure.")

    # ── 4. Sea-state rules (current conditions + 48 h outlook) ──
    wave_outlook = n48.get("wave_max_m") if n48.get("wave_max_m") is not None else wave_now
    if wave_now is not None:
        if wave_now >= 4.0 or (wave_outlook or 0) >= 4.0:
            reason("no_go", "high_waves",
                   f"🌊 Waves {wave_now:.1f} m now, up to {(wave_outlook or wave_now):.1f} m in 48 h "
                   "— beyond safe small-craft limits (≥ 4 m).")
        elif wave_now >= 2.5 or (wave_outlook or 0) >= 2.5:
            reason("caution", "waves_elevated",
                   f"🌊 Waves {wave_now:.1f} m (peak {(wave_outlook or wave_now):.1f} m) — "
                   "rough for small boats; stay alert.")
        else:
            reason("info", "waves_calm", f"🌊 Waves {wave_now:.1f} m — manageable.")

    if swell_now is not None and swell_now >= 2.5:
        reason("caution", "swell_high", f"〰️ Swell {swell_now:.1f} m — long-period rollers make beaching risky.")

    wind_outlook = n48.get("wind_max_kn") if n48.get("wind_max_kn") is not None else wind_now
    gust_outlook = n48.get("gust_max_kn") if n48.get("gust_max_kn") is not None else gust_now
    now_wind_txt = (
        f" Right now: {wind_now:.0f} kn sustained"
        + (f", gusts {gust_now:.0f} kn." if gust_now is not None else ".")
    ) if wind_now is not None else ""
    if gust_outlook is not None and gust_outlook >= 34:
        reason("no_go", "gale_gusts",
               f"💨 Gale-force gusts forecast, peak {gust_outlook:.0f} kn in next 48 h "
               f"(≥ WMO 34 kn gale warning).{now_wind_txt}")
    elif wind_outlook is not None and wind_outlook >= 20:
        reason("caution", "wind_strong",
               f"💨 Wind peak up to {wind_outlook:.0f} kn sustained (gusts {(gust_outlook or 0):.0f} kn) "
               f"in next 48 h — fresh-to-strong breeze; tiring for small craft.{now_wind_txt}")
    elif max(gust_now or 0, gust_outlook or 0) >= 28:
        # The advisory's own policy header (and the UI tile's red-warn
        # threshold) says gusts 28-34 kn = caution — but this branch was
        # never implemented, so the tile glowed red next to a glowing
        # "comfortable" text. Found via screenshot review (Chennai).
        g = max(gust_now or 0, gust_outlook or 0)
        reason("caution", "gusts_high",
               f"💨 Gusts to {g:.0f} kn (28-34 kn band) — secure loose gear, "
               "plan short trips; the sustained-wind number alone understates it.")
    elif wind_now is not None:
        # Always quote BOTH numbers — a "comfortable" label next to an
        # unmentioned 22 kn gust tile reads as a contradiction.
        g = gust_now if gust_now is not None else gust_outlook
        if g is not None and g >= 20:
            reason("info", "wind_ok",
                   f"💨 Wind {wind_now:.0f} kn sustained, gusts {g:.0f} kn — "
                   "manageable; small boats should mind the gusts, not the average.")
        elif g is not None:
            reason("info", "wind_ok",
                   f"💨 Wind {wind_now:.0f} kn, gusts {g:.0f} kn — comfortable.")
        else:
            reason("info", "wind_ok", f"💨 Wind {wind_now:.0f} kn — comfortable.")

    if current_kn is not None and current_kn > 3.0:
        reason("info", "current_strong",
               f"🌀 Surface current {current_kn} kn is unusually strong for open coast "
               "(typical: 0.5-2.5 kn) — could be a shallow coastal grid-cell reading. "
               "Verify against INCOIS current advisories before planning drift sets.")

    # ── 4b. Sky-condition rules (daily WMO code + rain chance) ──
    # Review round-6 EXTERNAL finding: this card used to decide purely
    # from wind + waves, so a verified thunderstorm-with-hail day (WMO 96,
    # 85% rain chance) still rendered "✅ GO" with NO storm bullet — while
    # the Weather agent and Marine Risk panels both flagged MODERATE for
    # the same point. The two most user-facing surfaces must never
    # disagree on whether it is safe to go out. The daily WMO weather
    # code and precipitation probability now feed real verdict floors.
    daily_wx: dict[str, Any] = {}
    try:
        # Lazy import (avoids any agents<->advisory import cycle); the
        # helper is ttlcache-cached, so a reason+advisory pair = 1 call.
        from pipeline.agents import weather as _wx_agent
        daily_wx = _wx_agent.get_daily_summary(lat, lon, target_date) or {}
        if daily_wx.get("wx_code") is not None:
            sources_used.append("Open-Meteo daily (WMO sky condition)")
    except Exception as e:  # noqa: BLE001
        sources_failed.append(f"daily sky condition: {type(e).__name__}: {e}")
    wx_code = daily_wx.get("wx_code")
    rain_chance = daily_wx.get("precip_probability_max")
    rain_txt = (f" (rain chance {rain_chance:.0f}%)"
                if rain_chance is not None else "")
    storm_blocked = False
    if wx_code == 99:
        storm_blocked = True
        reason("no_go", "hail_storm_severe",
               f"⛈️ Severe thunderstorm with HEAVY HAIL (WMO 99) expected today{rain_txt} — "
               "hail squalls can injure crew and punch holes in small craft. Stay on land.")
    elif wx_code == 96:
        storm_blocked = True
        reason("caution", "hail_storm",
               f"⛈️ Thunderstorm with HAIL (WMO 96) expected today{rain_txt} — hail and "
               "sudden squalls are dangerous for small open boats; delay departure or "
               "stay close to shelter.")
    elif wx_code == 95:
        storm_blocked = True
        reason("caution", "thunderstorm",
               f"⛈️ Thunderstorm expected today (WMO 95){rain_txt} — lightning + sudden "
               "squall risk on open water; watch the sky and be ready to head back.")
    elif wx_code in (65, 66, 67, 82):
        storm_blocked = True
        reason("caution", "heavy_rain_code",
               f"🌧️ Heavy rain/showers dominant today (WMO {wx_code}){rain_txt} — poor "
               "visibility and possible lightning; keep trips short and shore-side.")
    if not storm_blocked and rain_chance is not None and rain_chance >= 70:
        reason("info", "rain_chance_high",
               f"🌧️ Rain chance is high today ({rain_chance:.0f}%) — visibility may drop "
               "in bursts; protect electronics and plan for squalls.")

    if n24.get("rain_total_mm") is not None:
        rain24 = n24["rain_total_mm"]
        if rain24 >= 64.5:
            reason("no_go", "heavy_rain",
                   f"🌧️ {rain24:.0f} mm rain expected in 24 h — IMD 'heavy rain' class; "
                   "visibility and safe navigation compromised.")
        elif rain24 >= 35:
            reason("caution", "rain_moderate",
                   f"🌧️ {rain24:.0f} mm rain expected in 24 h — poor visibility at times.")

    if chl is not None and chl > 8:
        reason("caution", "bloom_level_chl",
               f"🦠 Chlorophyll {chl:.1f} mg/m³ — bloom-level; possible low-oxygen / HAB water, "
               "avoid fish from this patch until it clears.")

    # ── 5. Official INCOIS PFZ proximity ──
    nearest_pfz_km: float | None = None
    pfz_info: dict[str, Any] = {"found": False}
    try:
        pfz = incois_pfz.nearest_pfz(lat, lon)
        if pfz.get("found"):
            nearest_pfz_km = pfz["distance_km"]
            nm = pfz["distance_nm"]
            pfz_info = pfz
            sector = pfz.get("sector_name") or "coastal"
            compass = _deg_to_compass(pfz.get("bearing_deg"))
            reason("info", "official_pfz",
                   f"🎣 Official INCOIS PFZ ({sector} advisory, {pfz.get('advisory_date')}): "
                   f"{nm} NM {compass} of you (~{pfz['distance_km']:.0f} km).")
        else:
            pfz_info = pfz
            reason("info", "no_official_pfz", pfz.get("note", "No official PFZ line near this point today."))
    except Exception as e:  # noqa: BLE001
        reason("info", "pfz_check_failed", f"Official PFZ advisory unavailable right now ({type(e).__name__}).")

    # ── Verdict ──
    sevs = {r["severity"] for r in reasons}
    if "no_go" in sevs:
        verdict = "no_go"
    elif "caution" in sevs:
        verdict = "caution"
    else:
        verdict = "go"

    # ── Plain-language "samjhaane wali" summary ──
    # Fisherman-first: 3 short sentences a non-technical reader can act on.
    # Generated deterministically from the SAME variables + verdict —
    # no LLM, no paraphrasing that could drift from the numbers.
    plain_en: list[str] = []
    plain_hi: list[str] = []
    if verdict == "go":
        plain_en.append("✅ It looks safe to sail.")
        plain_hi.append("✅ Samundar mein jaana THEEK lag raha hai.")
    elif verdict == "caution":
        plain_en.append("⚠️ You may go, but only with extra care — stay close to shore.")
        plain_hi.append("⚠️ Jaa sakte hain, par bahut savdhani se — kinaare ke paas rahiye.")
    else:
        plain_en.append("⛔ Do NOT sail today. Stay on land.")
        plain_hi.append("⛔ Aaj samundar mein MAT jaiye. Zameen par rahiye.")
    top = sorted(
        [r for r in reasons if r["severity"] in ("no_go", "caution")],
        key=lambda r: 0 if r["severity"] == "no_go" else 1,
    )[:2]
    for r in top:
        plain_en.append(f"Why: {r['msg']}")
        plain_hi.append(f"Wajah: {r['msg']}")
    if not top and wave_now is not None and wind_now is not None:
        plain_en.append(
            f"Waves ~{wave_now:.1f} m and wind ~{wind_now:.0f} kn — both within safe limits."
        )
        plain_hi.append(
            f"Lehren ~{wave_now:.1f} m aur hawa ~{wind_now:.0f} kn — dono safe seema ke andar."
        )
    sw = safe_window
    if sw.get("found") and verdict != "no_go":
        _w0 = str(sw.get("from_utc") or "")[5:16].replace("T", " ")
        _w1 = str(sw.get("to_utc") or "")[5:16].replace("T", " ")
        plain_en.append(f"Best window: {_w0} → {_w1} UTC (the calmest stretch).")
        plain_hi.append(f"Sabse achha samay: {_w0} se {_w1} UTC tak (sabse shaant samay).")

    vt = {
        "go": {
            "icon": "✅", "color": "green",
            "headline_en": "GO — conditions look workable.",
            "headline_hi": "JA SAKTE HAIN — haalat theek hain.",
        },
        "caution": {
            "icon": "⚠️", "color": "amber",
            "headline_en": "CAUTION — go only with care.",
            "headline_hi": "SAVDHANI KE SAATH — dhyan se jaiye.",
        },
        "no_go": {
            "icon": "⛔", "color": "red",
            "headline_en": "NO-GO — stay on land today.",
            "headline_hi": "MAT JAIYE — aaj zameen par rahiye.",
        },
    }[verdict]

    valid_until = (started + timedelta(hours=ADVISORY_TTL_HOURS)).isoformat(timespec="seconds")
    return {
        "type": "advisory",
        "lat": lat,
        "lon": lon,
        "verdict": verdict,
        **vt,
        "headline": vt["headline_en"],
        "reasons": reasons,
        "variables": {
            "wave_height_m": wave_now,
            "swell_m": swell_now,
            "wind_kts": wind_now,
            "gust_kts": gust_now,
            "sst_c": sst_c,
            "sst_source": sst_source,
            "current_kn": current_kn,
            "current_dir": _deg_to_compass(now_f.get("current_dir_deg")),
            "chlorophyll_mg_m3": chl,
            "cyclone_dist_km": cyclone_dist_km,
            "cyclone_note": cyclone_note,
            "nearest_pfz_km": nearest_pfz_km,
            "nearest_pfz_nm": pfz_info.get("distance_nm"),
            "nearest_pfz_bearing": _deg_to_compass(pfz_info.get("bearing_deg")),
            "pfz_advisory_date": pfz_info.get("advisory_date"),
        },
        "outlook_48h": n48,
        "hourly_chart": hourly_chart,
        "plain_en": plain_en,
        "plain_hi": plain_hi,
        "safe_window": safe_window,
        "sources": sources_used,
        "sources_failed": sources_failed,
        "generated_at": started.isoformat(timespec="seconds"),
        "valid_until": valid_until,
        "disclaimer": (
            "Advisory only — final judgement rests with the skipper. "
            "Cross-check with the latest INCOIS/IMD bulletin before sailing."
        ),
    }
