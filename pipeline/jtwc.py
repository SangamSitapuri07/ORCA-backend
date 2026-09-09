"""JTWC tropical cyclone tracker — REAL active cyclones, no simulation.

Source: US Joint Typhoon Warning Center (Pearl Harbor), the WMO-designated
agency that issues tropical cyclone warnings for the North Indian Ocean
(basin code IO), Northwest Pacific (WP) and Southern Hemisphere (SH).

Feed:        https://www.metoc.navy.mil/jtwc/rss/jtwc.rss
Products:    https://www.metoc.navy.mil/jtwc/products/{id}web.txt

The RSS lists active systems with links to "web.txt" warning products.
Each web.txt is a plain-text WMO warning with a parseable position:

    WARNING POSITION:
    030000Z --- NEAR 23.8N 117.4E
    MOVEMENT PAST SIX HOURS - 295 DEGREES AT 10 KTS
    MAX SUSTAINED WINDS - 040 KT, GUSTS 050 KT
    RADIUS OF 034 KT WINDS - 040 NM NORTHEAST QUADRANT ...

Notes:
  - The .mil server blocks requests without a browser User-Agent
    (learned this the hard way — S3 AccessDenied otherwise).
  - A "FINAL WARNING" means the system has dissipated → we skip it.
  - If the feed is unreachable, we return cyclones=[] with an explicit
    error flag — we never pretend we checked when we didn't.
"""
from __future__ import annotations

import math
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

from pipeline.ttlcache import cached
from pipeline.incois_pfz import haversine_km, bearing_deg

RSS_URL = "https://www.metoc.navy.mil/jtwc/rss/jtwc.rss"
PRODUCT_URL = "https://www.metoc.navy.mil/jtwc/products/{pid}web.txt"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
SOURCE_LABEL = "JTWC (US Joint Typhoon Warning Center)"

BASIN_NAMES = {
    "wp": "Northwest Pacific",
    "io": "North Indian Ocean",
    "sh": "South Indian / South Pacific",
}
IO_BASIN = "io"

TTL_SEC = 30 * 60  # cyclone warnings update ~every 6 h; 30 min cache is safe

_PRODUCT_RE = re.compile(r"products/((wp|io|sh)(\d{2})(\d{2}))web\.txt", re.I)
_POS_RE = re.compile(
    r"WARNING POSITION:\s*\d{6}Z\s*---\s*NEAR\s*(\d+(?:\.\d+)?)\s*([NS])\s*(\d+(?:\.\d+)?)\s*([EW])"
)
_MOVE_RE = re.compile(r"MOVEMENT PAST SIX HOURS\s*-\s*(\d+)\s*DEG(?:REES)?\s*AT\s*(\d+)\s*KTS")
_WIND_RE = re.compile(r"MAX SUSTAINED WINDS\s*-\s*(\d+)\s*KT[,.]?\s*GUSTS\s*(\d+)\s*KT")
_R34_RE = re.compile(r"RADIUS OF 034 KT WINDS\s*-\s*(.+)QUADRANT", re.S)
_QUAD_RE = re.compile(r"(\d+)\s*NM\s*(?:NORTHEAST|SOUTHEAST|SOUTHWEST|NORTHWEST)\s*QUADRANT")


def _http_get(url: str, timeout: float = 12.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _intensity_label(kt: int) -> str:
    """IMD-style classification from sustained winds (kt)."""
    if kt >= 120:
        return "Super Cyclonic Storm"
    if kt >= 90:
        return "Extremely Severe Cyclonic Storm"
    if kt >= 64:
        return "Very Severe Cyclonic Storm"
    if kt >= 48:
        return "Severe Cyclonic Storm"
    if kt >= 34:
        return "Cyclonic Storm"
    if kt >= 28:
        return "Deep Depression"
    return "Depression"


def parse_warning_text(pid: str, text: str) -> dict[str, Any] | None:
    """Parse one JTWC web.txt product into a cyclone dict.

    Returns None for FINAL warnings (system dissipated) and unparsable text.
    Pure function — unit tests feed fixture text here without any network.
    """
    if "FINAL WARNING" in text[:600]:
        return None
    m = _POS_RE.search(text)
    if not m:
        return None
    lat_v, ns, lon_v, ew = m.groups()
    lat = float(lat_v) * (1 if ns.upper() == "N" else -1)
    lon = float(lon_v) * (1 if ew.upper() == "E" else -1)

    wind_kt = gust_kt = None
    mw = _WIND_RE.search(text)
    if mw:
        wind_kt, gust_kt = int(mw.group(1)), int(mw.group(2))

    move_deg = move_kt = None
    mm = _MOVE_RE.search(text)
    if mm:
        move_deg, move_kt = int(mm.group(1)), int(mm.group(2))

    r34_nm = None
    r34 = _R34_RE.search(text)
    if r34:
        quads = [int(q) for q in _QUAD_RE.findall(r34.group(0))]
        if quads:
            r34_nm = max(quads[:4])

    # storm name & number, e.g. "TROPICAL STORM 17W (SAUDEL) WARNING NR 047"
    name = advisory_no = None
    mt = re.search(r"SUBJ/[A-Z\s]*\d{2}[A-Z]\s*\(([^)]+)\)\s*(?:FINAL\s+)?WARNING\s*NR\s*(\d+)", text)
    if mt:
        name = mt.group(1).title()
        advisory_no = int(mt.group(2))

    basin = pid[:2].lower()
    num = pid[2:4]
    return {
        "id": pid.upper(),
        "basin": basin,
        "basin_name": BASIN_NAMES.get(basin, basin.upper()),
        "designation": f"{num}{'W' if basin == 'wp' else 'A' if basin == 'io' else 'S'}",
        "name": name,
        "advisory_no": advisory_no,
        "lat": lat,
        "lon": lon,
        "max_wind_kt": wind_kt,
        "gust_kt": gust_kt,
        "intensity": _intensity_label(wind_kt) if wind_kt else None,
        "movement_deg": move_deg,
        "movement_kt": move_kt,
        "radius_34kt_nm": r34_nm,
        "source": SOURCE_LABEL,
    }


def _fetch_now(basins: tuple[str, ...] = ("wp", "io", "sh")) -> dict[str, Any]:
    out: dict[str, Any] = {
        "source": SOURCE_LABEL,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cyclones": [],
        "errors": [],
    }
    try:
        rss = _http_get(RSS_URL)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"RSS feed unreachable: {type(e).__name__}: {e}")
        return out

    # Collect unique product ids mentioned anywhere in the RSS
    product_ids = sorted({m.group(1).lower() for m in _PRODUCT_RE.finditer(rss)})
    for pid in product_ids[:8]:  # never more than a handful active
        basin = pid[:2]
        if basins and basin not in basins:
            continue
        try:
            txt = _http_get(PRODUCT_URL.format(pid=pid))
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"{pid}: product unreachable ({type(e).__name__})")
            continue
        cyc = parse_warning_text(pid, txt)
        if cyc:
            out["cyclones"].append(cyc)
    return out


def get_active_cyclones(force: bool = False) -> dict[str, Any]:
    """All active JTWC-acknowledged tropical cyclones (cached 30 min)."""
    if force:
        from pipeline import ttlcache
        with ttlcache._lock:
            ttlcache._store.pop("jtwc", None)
    return cached("jtwc", TTL_SEC, _fetch_now)


def nearest_cyclone(lat: float, lon: float, basins: list[str] | None = None) -> dict[str, Any]:
    """Nearest active cyclone to a point, with honest structure:
      - checked: we successfully reached JTWC
      - found:   there is at least one active cyclone (in `basins` if given)
    """
    data = get_active_cyclones()
    reachable = not data["errors"] or bool(data["cyclones"])
    cyclones = data["cyclones"]
    if basins:
        cyclones = [c for c in cyclones if c["basin"] in basins]

    if not cyclones:
        return {
            "checked": reachable,
            "found": False,
            "advisories_anywhere": len(data["cyclones"]),
            "errors": data["errors"],
            "source": SOURCE_LABEL,
            "note": "No active tropical cyclone in the region right now."
            if reachable else "Could not reach JTWC to verify.",
        }

    best = min(cyclones, key=lambda c: haversine_km(lat, lon, c["lat"], c["lon"]))
    dist_km = haversine_km(lat, lon, best["lat"], best["lon"])
    return {
        "checked": True,
        "found": True,
        "distance_km": round(dist_km),
        "bearing_deg": round(bearing_deg(lat, lon, best["lat"], best["lon"])),
        "cyclone": best,
        "source": SOURCE_LABEL,
    }


def wind_model_note() -> str:
    return (
        "Cyclone hazard zone = reported position ± radius of 34-kt winds "
        "(the WMO gale-force threshold — small craft must avoid)."
    )
