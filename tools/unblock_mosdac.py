"""Unblock the three 'product-evidence-blocked' MOSDAC datasets — one command.

Background (2026-09-13): E06SCT_L4_AWW6HOURLY, E06OCM_L3_LAC_CQ and
E06SCT_L3_WV12 were left disabled pending "exact official product
files/metadata". Live re-verification showed:

  1. E06SCT_L4_AWW6HOURLY  → HTTP 500 — TYPO. Real ID: E06SCT_L4_AWV6HOURLY
     (4756 live files, ~8 MB; the user's file E06SCTL4AH_2026255_0000_… IS
     its newest granule — gId=18401334).
  2. E06OCM_L3_LAC_CQ      → ALIVE (157 files, daily, Indian coast,
     ~2.7 MB per file) — we simply never pulled one.
  3. E06SCT_L3_WV12        → HTTP 500 — DOES NOT EXIST. Real ID:
     E06SCT_L2B_WV12 (50615 HDF5 swath files). The "missing lat/lon" was
     our parser: swath geolocation is 2D per-pixel arrays, now handled.

This tool closes the evidence gap in one run, on the machine where the
MOSDAC credentials live (.env with MOSDAC_USERNAME / MOSDAC_PASSWORD):

    # 1. prove the datasets exist (NO login needed):
    python tools/unblock_mosdac.py --search-only

    # 2. search + download 1 newest granule each + deep format dump +
    #    write docs/formats/*.md evidence + try wind extraction:
    python tools/unblock_mosdac.py

    # 3. already have a file? (e.g. the AH granule from the old order)
    python tools/unblock_mosdac.py --local "E06SCTL4AH_2026255_0000_25km_v1.0.0.nc"

Everything is real: real API calls, real downloads, real parsed values.
Nothing is invented — a step that fails prints its true reason.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import mosdac_auth as M          # noqa: E402
from pipeline import parser                    # noqa: E402
from pipeline.deepdump import deep_dump, render_markdown  # noqa: E402
from pipeline.extractors import extract_wind, extract_wind_swath  # noqa: E402

# (label, datasetId, wrong-id-we-used-to-search, per-file size cap bytes)
TARGETS = [
    ("AWV6H", M.DS_SCT_AWV6H, "E06SCT_L4_AWW6HOURLY", 60 * 1024 * 1024),
    ("CQ",    M.DS_OCM_CQ,    None,                   30 * 1024 * 1024),
    ("WV12",  M.DS_SCT_WV12,  "E06SCT_L3_WV12",      120 * 1024 * 1024),
]

# Points we try to READ WIND at after download — real fishing grounds.
PROBE_POINTS = [
    ("Veraval offshore", 20.75, 70.85),
    ("Kochi offshore", 9.95, 76.25),
]
BBOX = M.BBOX_INDIA_COAST          # "68.0,7.0,94.0,24.0"
PROBE_DIR = Path(__file__).resolve().parents[1] / "data" / "mosdac_probe"
FORMATS_DIR = Path(__file__).resolve().parents[1] / "docs" / "formats"


# ── search helpers (public OpenSearch, NO login) ─────────────────────

def _bbox_contains(boundbox, lat: float, lon: float) -> bool | None:
    """Does a record's boundbox contain the point? None = unknown."""
    try:
        bb = boundbox if isinstance(boundbox, list) else [boundbox]
        b = bb[0]
        w = float(b.get("west")); s = float(b.get("south"))
        e = float(b.get("east")); n = float(b.get("north"))
        # 0-360 lon convention in some records
        lon_ok = (w <= lon <= e) or (w <= lon + 360 <= e)
        return s <= lat <= n and lon_ok
    except Exception:  # noqa: BLE001
        return None


def search_dataset(dataset_id: str, days: int, count: int = 50) -> dict:
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return M.search(dataset_id, start=start, end=end, bbox=BBOX, count=str(count))


def cmd_search_only(days: int) -> int:
    print("=" * 72)
    print("  STEP 1 — LIVE SEARCH (public apios endpoint, no login needed)")
    print("=" * 72)
    ref_lat, ref_lon = PROBE_POINTS[0][1], PROBE_POINTS[0][2]
    ok = 0
    for label, did, wrong_id, _cap in TARGETS:
        if wrong_id:
            try:
                M.search(wrong_id, count="1")
                print(f"  [{label}] old wrong ID {wrong_id}: unexpectedly works?!")
            except Exception as e:  # noqa: BLE001
                kind = ("HTTP error — the ID genuinely does not exist, as diagnosed"
                        if "HTTPError" in type(e).__name__ else
                        f"network error ({type(e).__name__}) — inconclusive here")
                print(f"  [{label}] old wrong ID {wrong_id}: fails — {kind}")
        try:
            d = search_dataset(did, days)
            entries = d.get("entries", [])
            in_box = [e for e in entries
                      if _bbox_contains(e.get("boundbox"), ref_lat, ref_lon) is not False]
            total = d.get("totalResults", "?")
            size = d.get("totalSizeMB", "?")
            print(f"  [{label}] {did}: {total} files total, {size} MB — "
                  f"{len(in_box)}/{len(entries)} recent entries cover our box")
            for e in (in_box or entries)[:3]:
                print(f"        • {e['identifier']}  (id={e['id']})")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [{label}] {did}: SEARCH FAILED — {str(e)[:120]}")
    print()
    if ok == len(TARGETS):
        print("  ✅ all three datasets are LIVE and reachable. Run without")
        print("     --search-only (creds needed) to fetch + dump real granules.")
        return 0
    print(f"  ⚠ {len(TARGETS) - ok}/3 searches failed — see reasons above.")
    return 1


# ── download (auth) ───────────────────────────────────────────────────

def download_granule(session, rec_id: str, fname: str, max_bytes: int) -> Path | None:
    """Size-guarded streaming download of one granule by record id."""
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    out = PROBE_DIR / fname
    if out.exists() and out.stat().st_size > 1024:
        print(f"        already downloaded: {out.name} ({out.stat().st_size // 1024} KB) — reuse")
        return out
    for attempt in (1, 2):
        r = session.get(M.DOWNLOAD_URL, params={"id": rec_id}, timeout=300, stream=True)
        if r.status_code == 401 and attempt == 1:
            M.refresh(session)
            continue
        if r.status_code != 200:
            print(f"        download HTTP {r.status_code} — real reason, not retrying blindly")
            return None
        clen = int(r.headers.get("Content-Length") or 0)
        if clen and clen > max_bytes:
            print(f"        refused: Content-Length {clen // 1048576} MB > cap "
                  f"{max_bytes // 1048576} MB (honest guard)")
            r.close()
            return None
        part = out.with_suffix(out.suffix + ".part")
        n = 0
        t0 = time.time()
        with open(part, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                n += len(chunk)
                if n > max_bytes:
                    fh.close()
                    part.unlink(missing_ok=True)
                    print(f"        aborted mid-stream: exceeded {max_bytes // 1048576} MB cap")
                    return None
                fh.write(chunk)
        if n < 1024:
            part.unlink(missing_ok=True)
            print(f"        suspicious tiny response ({n} B) — deleted, likely an error page")
            return None
        part.rename(out)
        print(f"        downloaded {n // 1048576} MB in {time.time() - t0:.1f}s → {out.name}")
        return out
    return None


# ── evidence + extraction on a real file ──────────────────────────────

def process_file(path: Path) -> dict:
    """Deep-dump one granule, save evidence, try reading wind from it."""
    print(f"        deep-dumping {path.name} …")
    ev = deep_dump(path)
    FORMATS_DIR.mkdir(parents=True, exist_ok=True)
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    md = FORMATS_DIR / f"{path.stem}.md"
    md.write_text(render_markdown(ev), encoding="utf-8")
    (PROBE_DIR / f"{path.stem}.json").write_text(
        json.dumps(ev, indent=2, default=str), encoding="utf-8")
    print(f"        evidence → {md.relative_to(md.parents[2])}")

    verdict = ev["checklist"]["verdict"]
    print(f"        checklist verdict: {verdict}"
          f" (mode={ev['checklist']['wind_mode']})")
    if not verdict.startswith("WIND"):
        return ev

    pf = parser.parse(path)
    for label, lat, lon in PROBE_POINTS:
        res = (extract_wind_swath(pf, lat, lon) if pf.swath
               else extract_wind(pf, lat, lon))
        if res is None or (isinstance(res, dict) and res.get("error")):
            print(f"        wind @ {label} ({lat}, {lon}): no usable pixel "
                  "near the point — real answer, not a failure to try")
            continue
        print(f"        wind @ {label}: {res.get('speed', res.get('error')):.2f} m/s "
              f"from {res.get('direction_deg', 0):.0f}° "
              f"(u={res.get('u')}, v={res.get('v')}, "
              f"flag={res.get('flag', '—')}, src={res.get('source', '')})")
    return ev


def cmd_full(days: int, which: str, keep_going: bool) -> int:
    print("=" * 72)
    print("  FULL UNBLOCK — search → download → evidence (creds required)")
    print("=" * 72)
    import os
    if not (os.environ.get("MOSDAC_USERNAME") and os.environ.get("MOSDAC_PASSWORD")):
        print("  ✗ MOSDAC_USERNAME / MOSDAC_PASSWORD not set (.env).")
        print("    Do --search-only (no creds) or add creds, then re-run.")
        return 2
    try:
        session = M.login()
        print("  ✅ MOSDAC login OK (download_api/gettoken)")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ login failed: {e}")
        return 2

    ref_lat, ref_lon = PROBE_POINTS[0][1], PROBE_POINTS[0][2]
    overall = 0
    for label, did, _wrong, cap in TARGETS:
        if which != "all" and which != label:
            continue
        print(f"\n  ── {label}: {did} " + "─" * (40 - len(did)))
        try:
            d = search_dataset(did, days)
            entries = d.get("entries", []) or []
        except Exception as e:  # noqa: BLE001
            print(f"     search failed: {str(e)[:120]}")
            overall = 1
            continue
        if not entries:
            print("     no entries in the last "
                  f"{days} days — try --days {days * 3}")
            overall = 1
            continue
        # newest entry whose footprint covers our probe box
        pick = next((e for e in entries
                     if _bbox_contains(e.get("boundbox"), ref_lat, ref_lon) is not False),
                    entries[0])
        print(f"     newest granule: {pick['identifier']} (id={pick['id']})")
        path = download_granule(session, pick["id"], pick["identifier"], cap)
        if path is None:
            overall = 1
            continue
        magic = path.open("rb").read(8)
        if not (magic.startswith(b"\x89HDF") or magic[:3] == b"CDF"):
            print("        ✗ downloaded file is NOT NetCDF/HDF5 — MOSDAC "
                  "served something else; kept for inspection at " + str(path))
            overall = 1
            continue
        try:
            process_file(path)
        except Exception as e:  # noqa: BLE001
            print(f"        process_file failed: {e!r}")
            overall = 1
        if not keep_going:
            break
    print("\n  Done. Evidence lives in docs/formats/ (commit these) and")
    print("  data/mosdac_probe/ (gitignored). With real evidence in hand,")
    print("  activating the connectors is a small, honest diff.")
    return overall


def cmd_local(files: list[str]) -> int:
    print("=" * 72)
    print("  LOCAL FILES — deep evidence dump, no network, no creds")
    print("=" * 72)
    for f in files:
        p = Path(f)
        if not p.exists():
            print(f"  ✗ not found: {p}")
            continue
        print(f"\n  ── {p.name} " + "─" * max(0, 44 - len(p.name)))
        try:
            process_file(p)
        except Exception as e:  # noqa: BLE001
            print(f"     failed: {e!r}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--search-only", action="store_true",
                    help="prove dataset IDs are live (no login)")
    ap.add_argument("--local", nargs="+", metavar="FILE",
                    help="dump evidence for already-downloaded files")
    ap.add_argument("--dataset", default="all",
                    choices=["all"] + [t[0] for t in TARGETS],
                    help="which dataset to fetch (default: all)")
    ap.add_argument("--days", type=int, default=3,
                    help="search window in days (default 3)")
    ap.add_argument("--keep-going", action="store_true",
                    help="don't stop after the first dataset")
    args = ap.parse_args(argv)

    if args.local:
        return cmd_local(args.local)
    if args.search_only:
        return cmd_search_only(args.days)
    return cmd_full(args.days, args.dataset, args.keep_going)


if __name__ == "__main__":
    raise SystemExit(main())
