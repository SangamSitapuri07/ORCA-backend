"""ISRO MOSDAC OCM-3 chlorophyll — LIVE, real-time, no frozen demo data. 🇮🇳

Why this exists: ORCA is an ISRO problem statement at Smart India
Hackathon — judges should see INDIA'S OWN satellite (EOS-06 / Oceansat-3,
OCM-3 sensor) inside the agent pipeline, pulled LIVE at click time.

Pipeline per query:

  1. MOSDAC login          — download_api/gettoken (official machine API,
                             token cached in-process, refreshed on 401)
  2. LIVE granule search   — /apios/datasets.json for E06OCM_L2C_LAC_OC
                             over the last N days around the point
  3. LIVE granule download — newest matching HDF5 file, size-guarded.
                             Files are kept only for the current UTC day
                             (auto-purged): today's click reuses today's
                             overpass once fetched; tomorrow is always
                             fetched fresh. Nothing is pre-baked.
  4. Point extraction      — parser.parse + extractors.extract_chlorophyll

Role in the pipeline: THIRD, independent chlorophyll source. NOAA ERDDAP
stays primary (global daily NRT), ESA OC-CCI cross-checks, MOSDAC adds
the high-resolution (1 km LAC) Indian view. When the first two are
cloud-masked, MOSDAC can still be primary — its messages say so.

Any failure (login down, no granule yet, slow link) returns an honest
error dict — never an invented value.

Self-test on the laptop (where the creds live):

    python -m pipeline.mosdac_ocm            # live login+search+download+extract
    python -m pipeline.mosdac_ocm --debug    # also print raw search-record keys
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pipeline import mosdac_auth
from pipeline.ttlcache import cached


SOURCE_LABEL = "ISRO MOSDAC EOS-06 OCM-3 (live 🇮🇳)"
DATASET = mosdac_auth.DS_OCM_OC  # E06OCM_L2C_LAC_OC

SEARCH_DAYS = 7            # look back up to a week for the newest granule
POINT_BBOX_DEG = 1.0       # search bbox half-width around the clicked point
# 75 s cap: with OC-CCI + anomaly + weather jobs running in parallel, a
# 90 s MOSDAC chain pushed total /reason time past the frontend's 90 s
# abort (Visakhapatnam 2026-09-04: backend finished into cache but the
# client had already shown a fake "unreachable" card).
JOB_BUDGET_SEC = 75.0      # whole live chain must fit inside the 110 s route deadline with headroom
DOWNLOAD_IDLE_TIMEOUT = 45 # abort if the stream stalls (slow demo wifi)
MAX_GRANULE_BYTES = 250_000_000  # honest guard — LAC L2C files are far smaller
# TOTAL wall-clock cap for one granule download. The idle timeout alone is
# NOT enough: a slow-but-alive connection (say 100 KB/s steady) would stream
# 60 MB for ~10 minutes while every click on that point waits behind the
# single-flight cache join — exactly how the laptop's inland-point clicks
# blew the 110 s route deadline and 504'd twice (2026-09-04 evening).
MAX_DL_WALL_SEC = 70.0

# How long a BACKGROUND drain thread may keep trickling after the request
# gave up. Daemon threads die with the process, so a stuck drain never
# wedges the backend — worst case its .part file is purged and the next
# click downloads fresh. 10 min absorbs even a 60 MB file at 100 KB/s.
MAX_DRAIN_SEC = 600.0
MAX_CONCURRENT_DRAINS = 3

GRANULE_DIR = Path(__file__).resolve().parent.parent / "data" / "mosdac_granules"

# Background-drain registry: rec_id -> thread / .part path being completed.
_DRAIN_LOCK = threading.Lock()
_DRAIN_THREADS: dict = {}
_DRAIN_PATHS: dict = {}


# ── enable / config ───────────────────────────────────────────────────

def mosdac_configured() -> bool:
    """Creds present? (mosdac_auth auto-loads .env into os.environ.)"""
    return bool(os.environ.get("MOSDAC_USERNAME") and os.environ.get("MOSDAC_PASSWORD"))


def mosdac_enabled() -> bool:
    """AUTO pattern like GFW: on when creds exist, off without them.
    ORCA_MOSDAC=1 forces it on (missing creds then surface as an honest
    error in the sources panel); ORCA_MOSDAC=0 disables completely."""
    forced = os.environ.get("ORCA_MOSDAC", "").strip().lower()
    if forced in ("0", "false", "off"):
        return False
    if forced in ("1", "true", "on"):
        return True
    return mosdac_configured()


# ── login session (cached, refresh-once) ──────────────────────────────

_session = None
_session_time = 0.0
_SESSION_TTL = 20 * 60  # 20 min — tokens outlive one demo easily


def _get_session():
    global _session, _session_time
    if _session is not None and time.time() - _session_time < _SESSION_TTL:
        return _session
    _session = mosdac_auth.login()
    _session_time = time.time()
    return _session


# ── search-record helpers ─────────────────────────────────────────────

_DATE_PATTERNS = (
    re.compile(r"(20\d{2})-(\d{2})-(\d{2})"),          # 2026-09-04
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),             # 20260904
    re.compile(r"(\d{1,2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(20\d{2})", re.I),  # 03SEP2026
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}


def granule_date(title: str) -> str | None:
    """Best-effort granule date (YYYY-MM-DD) from its title/filename."""
    for pat in _DATE_PATTERNS:
        m = pat.search(title or "")
        if not m:
            continue
        if pat is _DATE_PATTERNS[0] or pat is _DATE_PATTERNS[1]:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return f"{m.group(3)}-{_MONTHS[m.group(2).upper()]:02d}-{int(m.group(1)):02d}"
    return None


def _boundbox_contains(bbox_str: Any, lat: float, lon: float) -> bool | None:
    """Does the record's boundbox contain (lat, lon)?

    Live lesson 2026-09-04: MOSDAC's apios search IGNORES the boundingBox
    filter and happily returns the newest granules from OTHER regions
    (we got a Maldives/South-Arabian-Sea scene for a Veraval query).
    So every record must be filtered client-side BEFORE spending a
    download. Returns None when the field is missing/unparseable —
    unknown is not excluded (we'd rather try than silently skip).
    """
    if not bbox_str:
        return None
    vals = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(bbox_str))]
    if len(vals) < 4:
        return None
    if len(vals) == 4:
        # documented order: minLon, minLat, maxLon, maxLat
        return vals[0] <= lon <= vals[2] and vals[1] <= lat <= vals[3]
    # WKT polygon: alternating lon,lat pairs
    xs, ys = vals[0::2], vals[1::2]
    return min(xs) <= lon <= max(xs) and min(ys) <= lat <= max(ys)


def _records(search_json: dict) -> list[dict[str, Any]]:
    """Extract records defensively — MOSDAC's apios JSON shape has varied
    between releases; we look for the common containers and id fields."""
    recs = (search_json.get("records") or search_json.get("results")
            or search_json.get("entries") or [])
    out = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        rid = r.get("id") or r.get("recordId") or r.get("fileId") or r.get("fid")
        title = r.get("title") or r.get("fileName") or r.get("filename") or str(rid)
        # Live-verified 2026-09-04: MOSDAC apios `title` is just the
        # numeric id — the REAL granule date lives in dcDate / updated /
        # summary. Try the title first, then those fields.
        date_src = " ".join(str(r.get(k, "")) for k in ("dcDate", "updated", "published", "summary"))
        d = granule_date(str(title)) or granule_date(date_src)
        if rid is not None:
            out.append({"id": rid, "title": str(title), "date": d,
                        "boundbox": r.get("boundbox"), "raw": r})
    return out


# ── granule cache (same UTC day only, auto-purged) ────────────────────

def _purge_old_granules() -> None:
    if not GRANULE_DIR.exists():
        return
    cutoff = time.time() - 26 * 3600
    with _DRAIN_LOCK:
        active_parts = set(_DRAIN_PATHS.values())
    for f in GRANULE_DIR.glob("mosdac_*"):
        try:
            # .part debris = interrupted mid-download → never valid; drop
            # immediately (not just after 26 h) so a fresh attempt today
            # re-downloads instead of choking on the partial file.
            # EXCEPTION: a .part being actively completed by a background
            # drain thread is NOT debris — leave it alone.
            if f.name.endswith(".part"):
                if f not in active_parts:
                    f.unlink()
            elif f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def _silence_hdf5_diag() -> None:
    """Stop the HDF5 C layer from spewing raw HDF5-DIAG stacks to stderr.
    We handle EVERY open failure in Python and report honest one-line
    reasons — the C stack is pure console noise (a poisoned-cache open was
    printing a 20-line stack on every alerts tick/prewarm click)."""
    try:
        import h5py
        h5py.h5e.set_auto(h5py.h5e.H5E_DEFAULT, None, None)
    except Exception:  # noqa: BLE001
        pass


def _cache_entry_poisoned(path: Path) -> bool:
    """Integrity gate for same-day cache hits.

    A granule interrupted mid-download keeps its HDF5 signature but fails
    to open — the superblock records a stored_eof beyond the real size
    (seen live on the laptop: eof=15 MB vs stored_eof=60.5 MB). And
    parser.parse() NEVER raises ("fills warnings and returns"), so the
    poison surfaced downstream as a misleading 'no valid pixel' + endless
    console noise. Judge it AT THE GATE instead: HDF5-signature file that
    h5py cannot open = corrupt → purge → fresh download. Non-HDF5 files
    (e.g. classic netCDF-3) are NOT judged here — the parser decides."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    if not head.startswith(b"\x89HDF"):
        return False  # not HDF5-family — leave it to the parser, no churn
    _silence_hdf5_diag()
    try:
        import h5py
        with h5py.File(path, "r"):
            return False  # opens fine → healthy cache entry
    except Exception:  # noqa: BLE001
        return True


def _drain_in_background(r, tmp: Path, dest: Path, rec_id: Any,
                         started: float, prior_bytes: int) -> bool:
    """Hand a SLOW-BUT-ALIVE granule stream to a daemon thread that keeps
    trickling to completion after the request-side budget gave up.

    Why: MOSDAC's data host sometimes crawls (~100 KB/s). The 70 s wall
    cap protects the /reason deadline, but the honest "link crawling"
    error used to throw away the megabytes already fetched — so EVERY
    retry paid the full slow-download cost again and demo-day MOSDAC
    stayed red for hours. A daemon drain converts "server is slow today"
    into "this point's second click in ~10 min is an INSTANT same-day
    cache hit" — still 100% real MOSDAC bytes, zero invented data.

    Returns True if a drain was started (or one is already running).
    The drain thread touches ONLY this response object (never the shared
    session), writes to .part, and atomic-publishes on completion —
    partial files are still never served.
    """
    with _DRAIN_LOCK:
        if rec_id in _DRAIN_THREADS:
            return True  # already draining — one slow file, one thread
        if len(_DRAIN_THREADS) >= MAX_CONCURRENT_DRAINS:
            return False
        _DRAIN_PATHS[rec_id] = tmp

    def _run() -> None:
        total = prior_bytes
        try:
            with open(tmp, "ab") as fh:  # append where the request left off
                for chunk in r.iter_content(1 << 20):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_GRANULE_BYTES:
                        fh.close()
                        tmp.unlink(missing_ok=True)
                        return
                    fh.write(chunk)
                    if time.time() - started > MAX_DRAIN_SEC:
                        fh.close()
                        tmp.unlink(missing_ok=True)
                        print(f"[MOSDAC] background drain gave up after "
                              f"{MAX_DRAIN_SEC:.0f}s ({total/1e6:.1f} MB)", file=sys.stderr)
                        return
            tmp.replace(dest)  # atomic publish of the COMPLETE file
            if _cache_entry_poisoned(dest):
                dest.unlink(missing_ok=True)
                print(f"[MOSDAC] background drain finished but file fails HDF5 "
                      f"open — server truncated it; purged", file=sys.stderr)
                return
            print(f"[MOSDAC] background drain COMPLETE: {dest.name} "
                  f"({total/1e6:.1f} MB) — this point's next click = instant "
                  f"same-day cache hit", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            print(f"[MOSDAC] background drain died: {type(e).__name__}: "
                  f"{str(e)[:80]}", file=sys.stderr)
        finally:
            with _DRAIN_LOCK:
                _DRAIN_THREADS.pop(rec_id, None)
                _DRAIN_PATHS.pop(rec_id, None)

    t = threading.Thread(target=_run, name=f"mosdac-drain-{rec_id}", daemon=True)
    with _DRAIN_LOCK:
        _DRAIN_THREADS[rec_id] = t
    t.start()
    return True


def _find_cached_granule(rec_id: Any) -> Path | None:
    if GRANULE_DIR.exists():
        for f in GRANULE_DIR.glob(f"mosdac_{rec_id}*"):
            if f.name.endswith(".part"):  # incomplete download — not cache
                continue
            if f.stat().st_size > 0:
                return f
    return None


def _download_granule(session, rec_id: Any,
                      wall_cap_sec: float | None = None,
                      idle_cap_sec: float | None = None) -> tuple[Path | None, str | None, float]:
    """Live-download one granule from MOSDAC (same-day disk cache).

    Returns (path, error, seconds). Streams with an idle-timeout and a
    hard size guard so a flaky demo link fails HONESTLY instead of
    hanging the /reason deadline.

    wall_cap_sec / idle_cap_sec: the caller's REMAINING budget. Without
    these a 70 s slow-stream after a 50 s login+search ran past the
    outer 75 s job cap and surfaced as a nameless "timeout after 75s" —
    now the download dies inside its own cap and says exactly why.
    """
    wall_cap = MAX_DL_WALL_SEC if wall_cap_sec is None else max(5.0, min(MAX_DL_WALL_SEC, wall_cap_sec))
    idle_cap = max(8.0, min(DOWNLOAD_IDLE_TIMEOUT, idle_cap_sec if idle_cap_sec else DOWNLOAD_IDLE_TIMEOUT))
    connect_cap = max(5.0, min(20.0, wall_cap))
    started = time.time()
    hit = _find_cached_granule(rec_id)
    if hit is not None:
        if not _cache_entry_poisoned(hit):
            return hit, None, 0.0
        # poisoned cache (e.g. interrupted download from before the atomic
        # -publish fix) — purge on the spot and fall through to a FRESH
        # download. This is the gate-layer heal; the parser can never see
        # a corrupt file again (parser.parse never raises, so a downstream
        # hook could not be relied upon).
        try:
            hit.unlink()
        except OSError:
            pass

    _purge_old_granules()
    GRANULE_DIR.mkdir(parents=True, exist_ok=True)

    tmp: Path | None = None
    try:
        import requests  # local: pipeline dep already
        r = session.get(mosdac_auth.DOWNLOAD_URL, params={"id": rec_id},
                        timeout=(connect_cap, idle_cap), stream=True)
        if r.status_code == 401:
            session = mosdac_auth.refresh(session)
            r = session.get(mosdac_auth.DOWNLOAD_URL, params={"id": rec_id},
                            timeout=(connect_cap, idle_cap), stream=True)
        if r.status_code != 200:
            return None, f"download HTTP {r.status_code}", time.time() - started

        cd = r.headers.get("Content-Disposition", "")
        ext = ".h5"
        if "filename=" in cd:
            ext = Path(cd.split("filename=", 1)[1].strip('"').strip()).suffix or ".h5"
        dest = GRANULE_DIR / f"mosdac_{rec_id}{ext}"
        tmp = dest.with_name(dest.name + ".part")  # write-to-temp, atomic-publish

        total = 0
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                if chunk:
                    total += len(chunk)
                    if total > MAX_GRANULE_BYTES:
                        fh.close()
                        tmp.unlink(missing_ok=True)
                        return None, f"granule larger than {MAX_GRANULE_BYTES // 1_000_000} MB guard", time.time() - started
                    fh.write(chunk)
                    if time.time() - started > wall_cap:
                        fh.close()
                        # Request-side budget spent — but the stream is
                        # ALIVE and the bytes so far are real. Hand the
                        # rest to a background drain: it finishes the file
                        # to the same-day cache, so a retry in ~10 min is
                        # an instant hit instead of paying the whole slow
                        # download again. (100% real MOSDAC bytes; partial
                        # files are still never served.)
                        draining = _drain_in_background(r, tmp, dest, rec_id,
                                                        started, total)
                        note = ("download is finishing in the background — "
                                "retry this point in ~10 min (becomes an instant "
                                "same-day cache hit)" if draining else
                                "try again shortly (partial files are never cached)")
                        return None, (f"download too slow (> {wall_cap:.0f}s wall cap, "
                                    f"{total / 1_000_000:.1f} MB so far) — link crawling; "
                                    + note), time.time() - started
        # Publish ONLY on complete success: an interrupted run (network
        # drop, Ctrl+C, laptop lid) leaves a .part temp file, never a
        # broken "complete" granule in the cache. Caught live in the
        # laptop backend log (HDF5 'truncated file: eof=15MB, stored_eof=
        # 60.5MB') — a partial file kept being served from cache all day.
        tmp.replace(dest)
        # A server that CLOSES POLITELY mid-file (no exception) would
        # otherwise publish a truncated "complete" granule — re-verify the
        # just-downloaded file once at the gate (few 100 ms, once per file
        # per day) and reject honesty instead of poisoning the cache.
        if _cache_entry_poisoned(dest):
            try:
                dest.unlink()
            except OSError:
                pass
            return None, "download completed but file fails HDF5 open — server truncated it; try again", time.time() - started
        return dest, None, time.time() - started
    except Exception as e:  # noqa: BLE001
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        return None, f"{type(e).__name__}: {str(e)[:120]}", time.time() - started


# ── swath-aware direct reader (L2C LAC files) ─────────────────────────
# EOS-06 OCM-3 L2C LAC files are SWATH products: lat/lon are 2D grids
# tucked inside HDF5 groups (e.g. navigation_data/latitude), not root
# coordinates. The generic xarray extractor can't see those, so when it
# comes back empty we read the file directly with h5py.

_CHL_NAME_RE = re.compile(r"chlor|chl", re.I)


def _norm_lon_arr(lons, ref_lon):
    """Bring longitudes close to ref_lon by trying 0-360 convention."""
    import numpy as np
    l = np.asarray(lons, dtype="float64")
    if np.nanmin(l) >= 0 and ref_lon < 0:
        return l, ref_lon + 360
    return l, ref_lon


def _extract_chl_h5(path, lat: float, lon: float, max_ring: int = 40) -> dict[str, Any] | None:
    """Best-effort direct chlorophyll extraction from a MOSDAC HDF5 file.

    Returns None with no exception when the structure is unreadable —
    the caller reports the honest 'no valid pixel' line. Set
    _extract_chl_h5.last_debug for structure details."""
    import math

    import h5py
    import numpy as np

    dbg: dict[str, Any] = {"tried": []}
    _extract_chl_h5.last_debug = dbg

    with h5py.File(path, "r") as f:
        listing: list[str] = []
        f.visititems(lambda name, obj: listing.append(name)
                     if isinstance(obj, h5py.Dataset) else None)

    chl_name = next((n for n in listing if _CHL_NAME_RE.search(n.split("/")[-1])), None)
    if chl_name is None:
        dbg["tried"].append(f"no chlor var in {listing[:12]}")
        return None

    base = chl_name.rsplit("/", 1)[0] if "/" in chl_name else ""
    root = base.split("/")[0] if base else ""
    lat_cands = [n for n in listing if re.search(r"(^|/)(lat|latitude)$", n, re.I)]
    lon_cands = [n for n in listing if re.search(r"(^|/)(lon|longitude)$", n, re.I)]
    # prefer coords near the chlor group
    lat_cands.sort(key=lambda n: 0 if (root and n.startswith(root)) else 1)
    lon_cands.sort(key=lambda n: 0 if (root and n.startswith(root)) else 1)
    if not lat_cands or not lon_cands:
        dbg["tried"].append("no lat/lon datasets anywhere in file")
        return None

    for ln in lat_cands[:2]:
        for xn in lon_cands[:2]:
            try:
                with h5py.File(path, "r") as f:
                    lats = np.asarray(f[ln][()], dtype="float64")
                    lons = np.asarray(f[xn][()], dtype="float64")
                    chl = np.asarray(f[chl_name][()], dtype="float64")
                    attrs = dict(f[chl_name].attrs)
            except Exception as e:  # noqa: BLE001
                dbg["tried"].append(f"read {ln}/{xn}: {type(e).__name__}")
                continue
            if chl.ndim == 3:
                chl = chl[0]
            if chl.ndim != 2:
                dbg["tried"].append(f"chl shape {chl.shape} unexpected")
                continue
            lons, ref_lon = _norm_lon_arr(lons, lon)

            if lats.ndim == 2 and lats.shape == chl.shape:
                dist2 = (lats - lat) ** 2 + (lons - ref_lon) ** 2
                i0, j0 = np.unravel_index(np.nanargmin(dist2), dist2.shape)
                cell_lat = lambda i, j: lats[i, j]   # noqa: E731
                cell_lon = lambda i, j: lons[i, j]   # noqa: E731
            elif lats.ndim == 1 and lons.ndim == 1 \
                    and lats.shape[0] == chl.shape[0] and lons.shape[0] == chl.shape[1]:
                i0 = int(np.argmin(np.abs(lats - lat)))
                j0 = int(np.argmin(np.abs(lons - ref_lon)))
                cell_lat = lambda i, j: lats[i]      # noqa: E731
                cell_lon = lambda i, j: lons[j]      # noqa: E731
            else:
                dbg["tried"].append(f"coord shapes {lats.shape}/{lons.shape} vs chl {chl.shape}")
                continue

            # fill values: attrs of the chl dataset + usual sentinels
            fills = {9999.0, -32767.0, -9999.0, 1e30, -1e30, -999.0}
            for k in ("_FillValue", "missing_value", "fill_value"):
                if k in attrs:
                    try:
                        fills.add(float(np.asarray(attrs[k]).flat[0]))
                    except Exception:  # noqa: BLE001
                        pass

            # NetCDF-style packing: raw ints * scale_factor + add_offset.
            # h5py reads RAW values — we must unscale ourselves (h5netcdf
            # would do this automatically).
            scale = float(np.asarray(attrs.get("scale_factor", 1.0)).flat[0]) \
                if "scale_factor" in attrs else 1.0
            offset = float(np.asarray(attrs.get("add_offset", 0.0)).flat[0]) \
                if "add_offset" in attrs else 0.0
            units_raw = str(attrs.get("units", b"mg m^-3")).strip("b'\" ")
            is_log = "log" in units_raw.lower()

            def _ok(v: float) -> bool:
                if not np.isfinite(v) or v <= 0:
                    return False
                return not any(abs(v - fv) < 1e-3 or (fv != 0 and abs(v/fv - 1) < 1e-9) for fv in fills)

            def _real(v: float) -> float:
                out = v * scale + offset
                return float(10 ** out) if is_log else float(out)

            best = None
            best_d = float("inf")
            best_ring = 0
            best_ij = None
            # PIXEL FORENSICS: valid cells within ~ring 8 (~3 km at 360 m)
            # of the point — their median tells whether the chosen pixel is
            # a lone HOT pixel (cloud-contamination suspect) or part of a
            # genuinely high local patch. Reviewer asked us to stop hiding
            # 8x+ gaps behind a blanket "coastal bloom" story; this is the
            # evidence layer for that decision.
            neighbour_vals: list[float] = []
            for r in range(0, max_ring + 1):
                for di in range(-r, r + 1):
                    for dj in range(-r, r + 1):
                        if max(abs(di), abs(dj)) != r:
                            continue
                        i, j = i0 + di, j0 + dj
                        if not (0 <= i < chl.shape[0] and 0 <= j < chl.shape[1]):
                            continue
                        v = float(chl[i, j])
                        if not _ok(v):
                            continue
                        rv = _real(v)
                        if r <= 8:
                            neighbour_vals.append(rv)
                        d = math.hypot(cell_lat(i, j) - lat, cell_lon(i, j) - lon)
                        if d < best_d:
                            best, best_d, best_ring = rv, d, r
                            best_ij = (i, j)
                if best is not None and r >= max(best_ring, 8):
                    break  # nearest valid found AND full ~3 km neighbourhood scanned
            if best is None:
                dbg["tried"].append(f"all fill/masked within {max_ring} cells of point")
                continue
            if not (0.001 <= best <= 500):
                dbg["tried"].append(f"value {best} implausible after scaling")
                continue
            ring_median = float(np.median(neighbour_vals)) if neighbour_vals else None
            pixel_km = round(best_d * 111.0, 1)  # deg → km (approx, diagnostic only)
            ring_std = round(float(np.std(neighbour_vals)), 4) if neighbour_vals else None

            # WIDER-AREA context (~±40-pixel box): the decisive test for
            # "fine coastal structure". A real fine-scale bloom is HIGH HERE
            # but NORMAL 15 km away. If the wider area is uniformly high
            # too, a granule-level offset/bias is the likelier explanation.
            area_median = None
            area_valid = 0
            i_lo, i_hi = max(0, i0 - 40), min(chl.shape[0], i0 + 41)
            j_lo, j_hi = max(0, j0 - 40), min(chl.shape[1], j0 + 41)
            box = chl[i_lo:i_hi, j_lo:j_hi]
            b = box[np.isfinite(box)]
            b = b[b > 0]
            for fv in fills:
                b = b[np.abs(b - fv) >= 1e-3]
            if b.size:
                b = b * scale + offset
                if is_log:
                    b = 10 ** b
                b = b[np.isfinite(b) & (b > 0)]
            if b.size:
                area_median = round(float(np.median(b)), 4)
                area_valid = int(b.size)

            # CDOM at the SAME pixel (root-level band in L2C OC files) —
            # high CDOM marks optically complex case-2 water (river
            # runoff), where band-ratio chlorophyll algorithms disagree.
            cdom_val = cdom_units = None
            cdom_name = next((n for n in listing
                              if n.split("/")[-1].lower() == "cdom"), None)
            if cdom_name is not None and best_ij is not None:
                try:
                    bi, bj = best_ij
                    with h5py.File(path, "r") as f:
                        ds = f[cdom_name]
                        cattrs = dict(ds.attrs)
                        cv = float(ds[0, bi, bj] if ds.ndim == 3 else ds[bi, bj])
                    cfills = set()
                    for k in ("_FillValue", "missing_value", "fill_value"):
                        if k in cattrs:
                            try:
                                cfills.add(float(np.asarray(cattrs[k]).flat[0]))
                            except Exception:  # noqa: BLE001
                                pass
                    cs = float(np.asarray(cattrs["scale_factor"]).flat[0]) \
                        if "scale_factor" in cattrs else 1.0
                    co = float(np.asarray(cattrs["add_offset"]).flat[0]) \
                        if "add_offset" in cattrs else 0.0
                    if np.isfinite(cv) and not any(abs(cv - fv) < 1e-3 or
                                                   (fv != 0 and abs(cv / fv - 1) < 1e-9)
                                                   for fv in cfills):
                        cdom_val = round(cv * cs + co, 5)
                        cdom_units = str(cattrs.get("unit", cattrs.get("units", b""))).strip("b'\" ") or None
                except Exception:  # noqa: BLE001
                    pass

            dbg["pixel_km"] = pixel_km
            dbg["ring_valid"] = len(neighbour_vals)
            dbg["ring_median"] = ring_median
            dbg["ring_std"] = ring_std
            dbg["area_median"] = area_median
            dbg["cdom_value"] = cdom_val
            return {
                "value": best,
                "distance_deg": round(best_d, 4),
                "pixel_km": pixel_km,
                "ring_valid": len(neighbour_vals),
                "ring_median": round(ring_median, 4) if ring_median is not None else None,
                "ring_min": round(min(neighbour_vals), 4) if neighbour_vals else None,
                "ring_max": round(max(neighbour_vals), 4) if neighbour_vals else None,
                "ring_std": ring_std,
                "area_median": area_median,
                "area_valid": area_valid,
                "cdom_value": cdom_val,
                "cdom_units": cdom_units,
                "units": ("mg m^-3" if is_log else units_raw) or "mg m^-3",
            }
    return None

def get_chlorophyll(lat: float, lon: float, date: str | None = None) -> dict[str, Any]:
    """LIVE MOSDAC OCM-3 chlorophyll at (lat, lon).

    `date` accepted for interface parity — the live chain always uses the
    NEWEST granule from the last SEARCH_DAYS days; its true date is
    reported back, never invented."""
    if not mosdac_enabled():
        return {
            "error": "MOSDAC disabled (ORCA_MOSDAC=0 or no credentials configured)",
            "source": SOURCE_LABEL,
        }
    from pipeline.ttlcache import cached as _cached

    def _run() -> dict[str, Any]:
        res = _live_chain(lat, lon)
        if res.get("error"):
            # Failure is fine to show — but make sure rapid user retries
            # do NOT re-pay the whole login→search→download chain each
            # time (that's what made every re-click on the laptop stall
            # past the route deadline). Cached briefly; auto-clears.
            res = dict(res)
            res["error"] = res["error"] + " (retry pauses for 10 min — cached)"
        return res

    return _cached(
        f"mosdac_chl:{lat:.2f},{lon:.2f}",
        6 * 3600,  # same point+day = same newest granule; 6 h is honest
        _run,
        ttl_for=lambda r: 600.0 if r.get("error") else 6 * 3600.0,
    )


def _fail_message(why: str) -> str:
    """Compose the user-facing failure line, capped but NEVER cut
    mid-word (external reviewer flagged a literal 'no v' truncation,
    2026-09-07): prefer ending at a '; or ' candidate boundary, else
    at a whole word, and always say so with '; +more' / '…'."""
    prefix = "MOSDAC OCM-3 live fetch failed ("
    suffix = ") — NOAA primary is used"
    budget = 260 - len(prefix) - len(suffix)
    if len(why) <= budget:
        return prefix + why + suffix
    cut = why[:budget]
    sep = cut.rfind("; or ")
    if sep > budget // 2:
        cut = cut[:sep] + "; +more"
    else:
        cut = cut.rsplit(" ", 1)[0] + "…"
    return prefix + cut + suffix


_LAST_TRIED: list[str] = []       # per-candidate skip reasons of last chain run
_LAST_USED_PATH: str | None = None  # granule file that yielded the last value


def _live_chain(lat: float, lon: float) -> dict[str, Any]:
    # NOTE: `_LAST_USED_PATH = ...` below is an assignment, so without this
    # `global` it silently binds a FUNCTION-LOCAL shadow and the self-test's
    # --debug granule dump never prints (found via the 10.12N/80.62E run).
    global _LAST_USED_PATH
    t0 = time.time()
    _LAST_TRIED.clear()

    def _fail(why: str) -> dict[str, Any]:
        return {
            "error": _fail_message(why),
            "source": SOURCE_LABEL,
        }

    # 1) login
    t_login = time.time()
    try:
        session = _get_session()
    except mosdac_auth.MosdacAuthError as e:
        return _fail(f"login: {str(e).splitlines()[0][:90]}")
    login_secs = time.time() - t_login

    # 2) live search — newest granules overlapping the point
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=SEARCH_DAYS)
    bbox = f"{lon - POINT_BBOX_DEG},{lat - POINT_BBOX_DEG},{lon + POINT_BBOX_DEG},{lat + POINT_BBOX_DEG}"
    t_search = time.time()
    try:
        data = mosdac_auth.search(DATASET, start=start.isoformat(),
                                  end=end.isoformat(), bbox=bbox, count="40")
    except Exception as e:  # noqa: BLE001
        return _fail(f"search: {type(e).__name__}: {str(e)[:80]}")
    search_secs = time.time() - t_search
    print(f"[MOSDAC] login {login_secs:.1f}s · search {search_secs:.1f}s", file=sys.stderr)

    # Stage guard: if login+search alone swallowed the time budget (slow
    # link night), stop RIGHT HERE and name the stages — never drift
    # into the download phase and get namelessly killed by the outer
    # 75 s job cap ("timeout after 75s" with zero usable info).
    if time.time() - t0 > JOB_BUDGET_SEC - 25:
        return _fail(
            f"login ({login_secs:.0f}s) + search ({search_secs:.0f}s) alone ate the "
            f"{JOB_BUDGET_SEC:.0f}s budget — link is crawling right now; retry in a few "
            "minutes (failure pauses for 10 min, success caches 6 h)"
        )

    recs = _records(data)
    if not recs:
        return _fail(f"no {DATASET} granule found around the point in the last {SEARCH_DAYS} days")

    # newest first: parseable dates sort, unknowns keep server order last
    dated = [r for r in recs if r["date"]]
    dated.sort(key=lambda r: r["date"], reverse=True)
    ordered = dated + [r for r in recs if not r["date"]]

    # CLIENT-SIDE coverage filter — the search endpoint ignored our
    # boundingBox today (it returned a south-of-India scene for a Gujarat
    # point), so we verify each record's own boundbox before spending a
    # download on it. Records with unknown boundboxes are kept as
    # last-resort candidates.
    covering = [r for r in ordered if _boundbox_contains(r.get("boundbox"), lat, lon) is True]
    unknown_box = [r for r in ordered if _boundbox_contains(r.get("boundbox"), lat, lon) is None]
    skipped = len(ordered) - len(covering) - len(unknown_box)
    candidates = (covering + unknown_box)[:6]
    if not candidates:
        first = ordered[0].get("boundbox") if ordered else None
        return _fail(
            f"{len(recs)} granule(s) found but NONE covers this point "
            f"(newest covers {first}) — OCM-3 LAC scenes follow satellite passes; "
            f"this overpass was elsewhere. Retry later or pick a point under a recent pass"
        )

    # 3) live download + 4) extract — try newest → older until one parses
    tried: list[str] = []
    skipped_info: list[dict[str, Any]] = []  # {date, why} per failed candidate
    for rec in candidates:
        elapsed = time.time() - t0
        if elapsed > JOB_BUDGET_SEC - 25:
            return _fail(
                f"time budget exhausted before download finished (login {login_secs:.0f}s · "
                f"search {search_secs:.0f}s · earlier candidates also slow) — link crawling; "
                "any in-flight download keeps finishing in the background, so a retry "
                "in ~10 min should be an instant cache hit"
            )
        # Give THIS download exactly the budget that remains (minus parse
        # headroom) so the chain always returns with a PRECISE reason
        # inside the 75 s job cap instead of being namelessly killed.
        wall_cap = min(MAX_DL_WALL_SEC, JOB_BUDGET_SEC - elapsed - 8)
        path, derr, dl_secs = _download_granule(
            session, rec["id"], wall_cap_sec=wall_cap, idle_cap_sec=min(45.0, wall_cap))
        print(f"[MOSDAC] granule dl {dl_secs:.1f}s (cap {wall_cap:.0f}s)"
              + (f" — FAIL: {str(derr)[:90]}" if derr else ""), file=sys.stderr)
        if path is None:
            tried.append(f"{rec['id']}: {derr}")
            skipped_info.append({"date": rec["date"], "why": str(derr)})
            continue
        try:
            from pipeline import extractors, parser
            pf = parser.parse(path)
            val = extractors.extract_chlorophyll(pf, lat, lon)
        except Exception as e:  # noqa: BLE001
            why = f"parse {type(e).__name__}"
            # SELF-HEAL: a partially-downloaded granule in the same-day
            # cache can never become valid — purge it so the NEXT click
            # re-downloads fresh instead of re-failing loudly all day.
            if re.search(r"truncat|superblock|unable to (?:synchronously )?open|"
                         r"not a valid|signature", str(e), re.I):
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    pass
                why += " (truncated cached granule purged — will re-download on next click)"
            tried.append(f"{rec['id']}: {why}")
            skipped_info.append({"date": rec["date"], "why": why})
            continue
        via = "xarray"
        if val is None or val.get("value") is None:
            # L2C LAC files are swath products (2D lat/lon inside HDF5
            # groups) — the generic extractor can't see those; read the
            # file directly before giving up on it.
            try:
                direct = _extract_chl_h5(path, lat, lon)
            except Exception:  # noqa: BLE001
                direct = None
            if direct is not None and direct.get("value") is not None:
                val = direct
                via = "direct-swath"
        if val is None or val.get("value") is None:
            msg = f"{rec['id']}: no valid pixel near point"
            dbgd = getattr(_extract_chl_h5, "last_debug", None)
            if dbgd and dbgd.get("tried"):
                msg += f" [direct-reader: {dbgd['tried'][-1][:90]}]"
            tried.append(msg)
            skipped_info.append({"date": rec["date"], "why": "no valid pixel near point"})
            continue
        # transparency: if a NEWER covering granule exists but was unusable,
        # say so — the date of the value shown is never silently stale.
        _LAST_TRIED[:] = tried
        _LAST_USED_PATH = str(path)
        newer = [s for s in skipped_info
                 if s.get("date") and rec["date"] and s["date"] > rec["date"]]
        newer_txt = ""
        if newer:
            newer_txt = (f" | newer {newer[0]['date']} granule unusable today "
                         f"({str(newer[0]['why'])[:50]})")
        return {
            "value": val["value"],
            "units": val.get("units", "mg m^-3"),
            "lat": lat,
            "lon": lon,
            "distance_deg": val.get("distance_deg"),
            # pixel forensics (present when the direct-swath reader ran)
            "pixel_km": val.get("pixel_km"),
            "ring_valid": val.get("ring_valid"),
            "ring_median": val.get("ring_median"),
            "ring_min": val.get("ring_min"),
            "ring_max": val.get("ring_max"),
            "ring_std": val.get("ring_std"),
            "area_median": val.get("area_median"),
            "area_valid": val.get("area_valid"),
            "cdom_value": val.get("cdom_value"),
            "cdom_units": val.get("cdom_units"),
            "source": SOURCE_LABEL,
            "granule": rec["title"][:80],
            "date": rec["date"] or "latest per MOSDAC search",
            "live_download_s": round(dl_secs, 1) if dl_secs else None,
            "note": (f"ISRO EOS-06 OCM-3 (1 km), granule dated {rec['date'] or 'latest'} "
                     f"— pulled LIVE from MOSDAC on click"
                     + (f" ({dl_secs:.0f}s download)" if dl_secs else " (today's granule already fetched)")
                     + (f", read via {via}" if via == "direct-swath" else "")
                     + newer_txt),
        }

    msg = "; or ".join(tried) if tried else "no usable granule"
    if skipped:
        msg = f"{skipped} outside-area granule(s) skipped. " + msg
    return _fail(msg)


# ── self-test ─────────────────────────────────────────────────────────

def _debug_stats(path, lat: float, lon: float) -> None:
    """Print the granule's real coverage + fill stats — the decisive
    answer to 'was the point even inside this file, and how cloudy was
    it?'"""
    import h5py
    import numpy as np
    with h5py.File(path, "r") as f:
        names: list[str] = []
        f.visititems(lambda n, o: names.append(n) if isinstance(o, h5py.Dataset) else None)
        print("     --debug datasets:")
        for n in names[:40]:
            print(f"        {n}  shape={f[n].shape}")
        lat_d = next((n for n in names if n.split("/")[-1].lower() in ("lat", "latitude")), None)
        lon_d = next((n for n in names if n.split("/")[-1].lower() in ("lon", "longitude")), None)
        chl_d = next((n for n in names if _CHL_NAME_RE.search(n.split("/")[-1])), None)
        if lat_d and lon_d:
            la, lo = f[lat_d][()], f[lon_d][()]
            print(f"     --debug lat range: {np.nanmin(la):.3f} .. {np.nanmax(la):.3f} | "
                  f"lon range: {np.nanmin(lo):.3f} .. {np.nanmax(lo):.3f}")
            print(f"     --debug point ({lat}, {lon}) inside coverage: "
                  f"{np.nanmin(la) <= lat <= np.nanmax(la) and np.nanmin(lo) <= lon <= np.nanmax(lo)}")
        if chl_d:
            arr = np.asarray(f[chl_d][()], dtype="float64")
            attrs = dict(f[chl_d].attrs)
            print(f"     --debug {chl_d} attrs: {dict(list(attrs.items())[:6])}")
            fv = float(np.asarray(attrs.get('_FillValue', np.nan)).flat[0]) if '_FillValue' in attrs else None
            finite = np.isfinite(arr)
            fillm = (arr == fv) if fv is not None else False
            valid = finite & ~fillm & (arr > 0)
            print(f"     --debug CHL cells: total={arr.size}, finite={finite.sum()} "
                  f"({100*finite.mean():.0f}%), positive-valid={valid.sum()} ({100*valid.mean():.0f}%), "
                  f"fill={fillm.sum() if fv else 'n/a'}")


def _selftest() -> int:
    print("=" * 68)
    print("  MOSDAC OCM-3 LIVE self-test — login -> search -> download -> extract")
    print("  (credentials never printed; everything fetched RIGHT NOW)")
    print("=" * 68)
    if not mosdac_configured():
        print("  X MOSDAC_USERNAME/PASSWORD not set (.env). Aborting.")
        return 2
    print("  creds: found (hidden)")

    # default = Veraval (PFZ validation ground); --lat/--lon override for
    # testing offshore points (coastal cells are land-masked by nature)
    lat, lon = 20.9, 70.37
    if "--lat" in sys.argv and "--lon" in sys.argv:
        lat = float(sys.argv[sys.argv.index("--lat") + 1])
        lon = float(sys.argv[sys.argv.index("--lon") + 1])
    print(f"  point: {lat}N {lon}E")

    print(f"  1) LIVE search {DATASET}, last {SEARCH_DAYS} days around ({lat}N {lon}E)...")
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=SEARCH_DAYS)
    bbox = f"{lon - POINT_BBOX_DEG},{lat - POINT_BBOX_DEG},{lon + POINT_BBOX_DEG},{lat + POINT_BBOX_DEG}"
    try:
        t_s = time.time()
        data = mosdac_auth.search(DATASET, start=start.isoformat(),
                                  end=end.isoformat(), bbox=bbox, count="40")
        recs = _records(data)
        print(f"     ✅ {len(recs)} granule(s) found ({data.get('totalResults', '?')} total, {time.time()-t_s:.1f}s)")
        if "--debug" in sys.argv and recs:
            print("     --debug first record keys:", sorted(recs[0]["raw"].keys()))
            print("     --debug id/title:", recs[0]["id"], "|", recs[0]["title"][:70])
        for r in recs[:5]:
            c = _boundbox_contains(r.get("boundbox"), lat, lon)
            mark = "covers-point ✓" if c is True else ("OUTSIDE ✗" if c is False else "box unknown")
            print(f"       - {r['title'][:40]}  (date: {r['date'] or '?'}, {mark})")
    except Exception as e:  # noqa: BLE001
        print(f"     X search failed: {type(e).__name__}: {e}")
        return 1

    print("  2) LIVE login + newest-granule download + point extract (may take 20-90s)...")
    t0 = time.time()
    res = _live_chain(lat, lon)
    dt = time.time() - t0
    if res.get("value") is not None:
        print(f"     ✅ chlorophyll {res['value']:.3f} {res.get('units')} at point")
        print(f"        granule: {res.get('granule')}")
        print(f"        granule date: {res.get('date')} | live download: {res.get('live_download_s') or 0}s | total: {dt:.1f}s")
        print(f"        note: {res.get('note')}")
        if res.get("pixel_km") is not None:
            print(f"        pixel forensics: chosen pixel ~{res['pixel_km']} km from point; "
                  f"{res.get('ring_valid')} pixel(s) within ~3 km read ~{res.get('ring_median')}" +
                  (f" (min {res.get('ring_min')}, max {res.get('ring_max')}, "
                   f"std {res.get('ring_std')} — std≈0 = suspiciously flat)"
                   if res.get("ring_std") is not None else ""))
            if res.get("area_median") is not None:
                print(f"        wider area (~±40-pixel box): {res.get('area_valid')} valid pixel(s), "
                      f"median {res.get('area_median')}")
            if res.get("cdom_value") is not None:
                print(f"        CDOM at pixel: {res.get('cdom_value')} {res.get('cdom_units') or ''} "
                      f"(high CDOM = optically complex case-2 water — chl algorithms disagree there)")
            print("        (read this: pixel far from point = drift suspect; lone HOT pixel vs its")
            print("         ~3 km neighbourhood = cloud-contamination suspect; wider-area median HIGH")
            print("         like the pixel = granule-level offset, NOT fine structure; wider-area")
            print("         normal = OCM-3 genuinely sees a small sharp patch)")
        if "--debug" in sys.argv:
            for t in _LAST_TRIED:
                print(f"        --debug skipped candidate: {t}")
            if _LAST_USED_PATH:
                _debug_stats(_LAST_USED_PATH, lat, lon)
        print("  MOSDAC LIVE pipeline READY — agents will show ISRO data on clicks. 🇮🇳")
        return 0
    print(f"     X live chain failed: {res.get('error')}")
    if "--debug" in sys.argv:
        dbgd = getattr(_extract_chl_h5, "last_debug", None) or {}
        print("     --debug direct-reader attempts:", dbgd.get("tried"))
        # decisive diagnostics: coverage, fill stats, attrs
        try:
            files = sorted(GRANULE_DIR.glob("mosdac_*"), key=lambda p: -p.stat().st_mtime)
            if files:
                print(f"     --debug structure + stats of {files[0].name}:")
                _debug_stats(files[0], lat, lon)
                print("     --debug TIP: if the point is outside coverage or the valid-fraction")
                print("                  is tiny (monsoon clouds), retry OFFSHORE, e.g.:")
                print("                  python -m pipeline.mosdac_ocm --debug --lat 20.2 --lon 70.0")
        except Exception as e:  # noqa: BLE001
            print("     --debug stats failed:", e)
    print("       (server busy or no fresh granule yet — agents will show this")
    print("        honest message and keep using NOAA primary. Re-run later.)")
    return 1


if __name__ == "__main__":
    sys.exit(_selftest())
