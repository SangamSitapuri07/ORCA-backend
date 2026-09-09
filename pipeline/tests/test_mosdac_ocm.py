"""Tests for the ISRO MOSDAC OCM-3 LIVE adapter (all mocked — no network,
no real credentials; the honest live proof is `python -m pipeline.mosdac_ocm`
on a machine that has the creds)."""
from __future__ import annotations

import pytest
import time

from pipeline import mosdac_ocm, mosdac_auth


@pytest.fixture(autouse=True)
def _no_real_creds(monkeypatch):
    monkeypatch.delenv("MOSDAC_USERNAME", raising=False)
    monkeypatch.delenv("MOSDAC_PASSWORD", raising=False)
    monkeypatch.delenv("ORCA_MOSDAC", raising=False)
    yield


def test_disabled_without_creds():
    assert mosdac_ocm.mosdac_enabled() is False
    monkey = dict(os_environ=False)
    assert mosdac_ocm.mosdac_configured() is False


def test_enabled_with_creds(monkeypatch):
    monkeypatch.setenv("MOSDAC_USERNAME", "u")
    monkeypatch.setenv("MOSDAC_PASSWORD", "p")
    assert mosdac_ocm.mosdac_enabled() is True


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("MOSDAC_USERNAME", "u")
    monkeypatch.setenv("MOSDAC_PASSWORD", "p")
    monkeypatch.setenv("ORCA_MOSDAC", "0")
    assert mosdac_ocm.mosdac_enabled() is False
    monkeypatch.setenv("ORCA_MOSDAC", "1")
    assert mosdac_ocm.mosdac_enabled() is True


def test_granule_date_formats():
    assert mosdac_ocm.granule_date("E06OCM_L2C_LAC_OC_03SEP2026_...h5") == "2026-09-03"
    assert mosdac_ocm.granule_date("chlor_2026-09-03_LAC") == "2026-09-03"
    assert mosdac_ocm.granule_date("xyz_20260903") == "2026-09-03"
    assert mosdac_ocm.granule_date("no-date-here") is None


def test_records_defensive_shapes():
    j = {"records": [{"id": 42, "title": "E06OCM_L2C_LAC_OC_03SEP2026.h5"}]}
    recs = mosdac_ocm._records(j)
    assert len(recs) == 1 and recs[0]["id"] == 42
    assert recs[0]["date"] == "2026-09-03"
    assert mosdac_ocm._records({"totalResults": 0}) == []
    # alternate containers + id keys shouldn't crash
    j2 = {"results": [{"recordId": "abc", "fileName": "f_2026-09-01"}]}
    recs2 = mosdac_ocm._records(j2)
    assert recs2[0]["id"] == "abc" and recs2[0]["date"] == "2026-09-01"


def _patch_live_world(monkeypatch, extractor_value):
    monkeypatch.setenv("MOSDAC_USERNAME", "u")
    monkeypatch.setenv("MOSDAC_PASSWORD", "p")
    # reset the module-level session cache — one test's login must not
    # leak into the next
    monkeypatch.setattr(mosdac_ocm, "_session", None)
    monkeypatch.setattr(mosdac_ocm, "_session_time", 0.0)
    monkeypatch.setattr(mosdac_auth, "login", lambda: object())
    monkeypatch.setattr(
        mosdac_auth, "search",
        lambda *a, **k: {"totalResults": 1, "records": [
            {"id": 991, "title": "E06OCM_L2C_LAC_OC_03SEP2026_x.h5"}]})
    monkeypatch.setattr(
        mosdac_ocm, "_download_granule",
        # **kw: the chain now passes the REMAINING time budget as
        # wall_cap_sec / idle_cap_sec — the stub must accept it.
        lambda session, rid, **kw: ("/tmp/fake_mosdac_granule.h5", None, 12.3))
    import pipeline.parser as parser
    import pipeline.extractors as extractors
    monkeypatch.setattr(parser, "parse", lambda path: object())
    monkeypatch.setattr(extractors, "extract_chlorophyll",
                        lambda pf, lat, lon, debug=False: extractor_value)


def test_live_chain_success(monkeypatch):
    _patch_live_world(monkeypatch, {
        "value": 0.77, "units": "mg m^-3", "distance_deg": 0.004})
    res = mosdac_ocm._live_chain(20.9, 70.37)
    assert res["value"] == 0.77
    assert res["date"] == "2026-09-03"
    assert res["source"] == mosdac_ocm.SOURCE_LABEL
    assert "LIVE" in res["note"]
    assert res["live_download_s"] == 12.3


def test_live_chain_sets_module_used_path_for_debug_dump(monkeypatch):
    """Regression: `_LAST_USED_PATH = ...` inside _live_chain needs a
    `global` declaration — without it the assignment binds a function-local
    shadow and the self-test's --debug granule dump silently never prints
    (seen live on the 10.12N/80.62E run)."""
    _patch_live_world(monkeypatch, {
        "value": 0.77, "units": "mg m^-3", "distance_deg": 0.004})
    mosdac_ocm._LAST_USED_PATH = None
    mosdac_ocm._live_chain(20.9, 70.37)
    assert mosdac_ocm._LAST_USED_PATH == "/tmp/fake_mosdac_granule.h5"


def test_live_chain_honest_when_no_granule(monkeypatch):
    _patch_live_world(monkeypatch, None)
    # search returns nothing this time
    monkeypatch.setattr(mosdac_auth, "search", lambda *a, **k: {"totalResults": 0, "records": []})
    res = mosdac_ocm._live_chain(20.9, 70.37)
    assert res.get("value") is None
    assert "live fetch failed" in res["error"]
    assert "no E06OCM_L2C_LAC_OC granule" in res["error"]


def test_live_chain_honest_when_pixel_missing(monkeypatch):
    _patch_live_world(monkeypatch, None)  # extractor finds no valid pixel
    res = mosdac_ocm._live_chain(20.9, 70.37)
    assert res.get("value") is None
    assert "no valid pixel" in res["error"]
    assert "NOAA primary" in res["error"]


def test_live_chain_login_error_is_honest(monkeypatch):
    _patch_live_world(monkeypatch, None)
    def _boom():
        raise mosdac_auth.MosdacAuthError("401 Unauthorized: wrong username/password")
    monkeypatch.setattr(mosdac_auth, "login", _boom)
    res = mosdac_ocm._live_chain(20.9, 70.37)
    assert "login" in res["error"]
    assert "401" in res["error"]


# ── swath direct-reader on a SYNTHETIC HDF5 granule ────────────────────

def test_extract_chl_h5_swath_2d(tmp_path):
    """Simulates an EOS-06 OCM-3 L2C LAC file: 2D lat/lon inside groups,
    land-masked near the point, one valid pixel a few cells away."""
    h5py = __import__("h5py")
    import numpy as np
    p = tmp_path / "fake_ocm3.h5"
    with h5py.File(p, "w") as f:
        lats, lons = np.meshgrid(np.linspace(20.0, 21.0, 20),
                                 np.linspace(70.0, 71.0, 20), indexing="ij")
        f.create_dataset("navigation_data/latitude", data=lats)
        f.create_dataset("navigation_data/longitude", data=lons)
        chl = np.full((20, 20), -32767.0)
        chl[14, 5] = 0.83  # one valid clear-water pixel
        d = f.create_dataset("geophysical_data/chlor_a", data=chl)
        d.attrs["_FillValue"] = -32767.0
        d.attrs["units"] = "mg m^-3"
    res = mosdac_ocm._extract_chl_h5(str(p), 20.5, 70.5)
    assert res is not None and abs(res["value"] - 0.83) < 1e-6
    assert res["distance_deg"] < 0.4
    assert "mg" in res["units"]


def test_extract_chl_h5_pixel_forensics(tmp_path):
    """Review round-5 (2026-09-05): an 8x+ OCM-3-vs-NOAA gap must be
    DIAGNOSABLE — the extractor reports how far the chosen pixel drifted
    and what its own ~3 km neighbourhood reads, so the agent can tell a
    lone HOT pixel (cloud-contamination suspect) from a genuinely high
    patch. Grid reads 0.40 everywhere except one hot 3.20 pixel exactly
    at the query point."""
    h5py = __import__("h5py")
    import numpy as np
    p = tmp_path / "hot_pixel.h5"
    n = 30
    with h5py.File(p, "w") as f:
        lats, lons = np.meshgrid(np.linspace(10.0, 10.3, n),
                                 np.linspace(80.5, 80.8, n), indexing="ij")
        f.create_dataset("latitude", data=lats)
        f.create_dataset("longitude", data=lons)
        chl = np.full((n, n), 0.40)
        chl[15, 15] = 3.20  # lone hot pixel at the query point
        f.create_dataset("CHL", data=chl)
    # point maps exactly onto cell [15, 15] (step = 0.3/29)
    res = mosdac_ocm._extract_chl_h5(str(p), 10.0 + 15 * 0.3 / 29, 80.5 + 15 * 0.3 / 29)
    assert res is not None
    assert abs(res["value"] - 3.20) < 1e-6        # the exact pixel is picked
    assert res["pixel_km"] < 2.0                  # …right at the point
    assert res["ring_valid"] > 100                # whole ~3 km neighbourhood valid
    assert abs(res["ring_median"] - 0.40) < 1e-6  # …and it reads LOW → hot pixel


def test_extract_chl_h5_flat_field_area_and_cdom(tmp_path):
    """Review round-5b: the 10.12N/80.62E granule read ~3.0 UNIFORMLY over
    its 3 km neighbourhood. The extractor must now (a) report ring spread
    (std≈0 exposes the flatness), (b) report the wider ~±40-pixel area
    median — the decisive test that rules out 'fine coastal structure' —
    and (c) sample the CDOM band at the same pixel (case-2 water flag)."""
    h5py = __import__("h5py")
    import numpy as np
    p = tmp_path / "flat_high.h5"
    n = 120  # big enough for the ±40-pixel area box
    with h5py.File(p, "w") as f:
        lats, lons = np.meshgrid(np.linspace(10.0, 10.3, n),
                                 np.linspace(80.5, 80.8, n), indexing="ij")
        f.create_dataset("latitude", data=lats)
        f.create_dataset("longitude", data=lons)
        f.create_dataset("CHL", data=np.full((n, n), 3.0))      # uniformly high
        cd = f.create_dataset("CDOM", data=np.full((n, n), 0.42))
        cd.attrs["unit"] = "m^-1"
    res = mosdac_ocm._extract_chl_h5(str(p), 10.15, 80.65)
    assert res is not None
    assert abs(res["value"] - 3.0) < 1e-6
    assert res["pixel_km"] < 2.0                 # exact pixel, no drift
    assert res["ring_valid"] == 289              # 17x17 neighbourhood, all valid
    assert res["ring_std"] < 1e-6                # suspiciously flat
    assert res["area_median"] == 3.0             # wider area uniformly high too
    assert res["area_valid"] > 3000
    assert abs(res["cdom_value"] - 0.42) < 1e-6 and res["cdom_units"] == "m^-1"


def test_extract_chl_h5_all_masked_returns_none(tmp_path):
    h5py = __import__("h5py")
    import numpy as np
    p = tmp_path / "masked.h5"
    with h5py.File(p, "w") as f:
        lats, lons = np.meshgrid(np.linspace(20.0, 21.0, 12),
                                 np.linspace(70.0, 71.0, 12), indexing="ij")
        f.create_dataset("geolocation/lat", data=lats)
        f.create_dataset("geolocation/lon", data=lons)
        f.create_dataset("geophysical_data/chl", data=np.full((12, 12), -999.0))
    assert mosdac_ocm._extract_chl_h5(str(p), 20.5, 70.5) is None


# ── atomic download + self-healing cache (truncated-file bug, laptop log) ──

class _FakeResp:
    def __init__(self, chunks, boom_after=None):
        self.status_code = 200
        self.headers = {"Content-Disposition": 'filename="granule.h5"'}
        self._chunks = chunks
        self._boom_after = boom_after

    def iter_content(self, size):
        for i, c in enumerate(self._chunks):
            if self._boom_after is not None and i >= self._boom_after:
                raise ConnectionError("network dropped mid-stream")
            yield c


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp

    def get(self, *a, **k):
        return self._resp


def test_download_atomic_publish_failure_leaves_no_partials(tmp_path, monkeypatch):
    """Laptop backend log: an interrupted download left a 15 MB truncated
    granule (stored_eof 60.5 MB) that the cache kept serving all day with
    HDF5 errors. Now: download goes to .part, published only on success."""
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    resp = _FakeResp([b"partial-data-" * 100], boom_after=1)
    session = _FakeSession(resp)
    # iter_content yields chunk 0 (writes it), then raises at index 1
    resp._chunks = [b"x" * 100, b"y" * 100]
    resp._boom_after = 1
    path, err, _ = mosdac_ocm._download_granule(session, 555)
    assert path is None and err is not None
    assert not (tmp_path / "mosdac_555.h5").exists()       # never published
    assert not (tmp_path / "mosdac_555.h5.part").exists()  # debris cleaned
    assert mosdac_ocm._find_cached_granule(555) is None


def test_download_atomic_publish_success_and_cache_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    resp = _FakeResp([b"a" * 100, b"b" * 100])
    path, err, _ = mosdac_ocm._download_granule(_FakeSession(resp), 777)
    assert err is None and path.name == "mosdac_777.h5"
    assert (tmp_path / "mosdac_777.h5").stat().st_size == 200
    assert not list(tmp_path.glob("*.part"))
    assert mosdac_ocm._find_cached_granule(777) == path


def test_part_files_are_never_cache_and_purged_immediately(tmp_path, monkeypatch):
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    part = tmp_path / "mosdac_888.h5.part"
    part.write_bytes(b"interrupted")
    assert mosdac_ocm._find_cached_granule(888) is None   # .part ≠ complete
    mosdac_ocm._purge_old_granules()
    assert not part.exists()  # fresh debris dropped right away, not in 26 h


def test_live_chain_purges_truncated_cache_file(tmp_path, monkeypatch):
    """One poisoned file must self-heal: parse raises a truncation error →
    chain deletes the file so the next click re-downloads fresh."""
    _patch_live_world(monkeypatch, None)
    poisoned = tmp_path / "mosdac_991.h5"
    poisoned.write_bytes(b"truncated")
    monkeypatch.setattr(
        mosdac_ocm, "_download_granule",
        lambda session, rid, **kw: (poisoned, None, 0.0))
    import pipeline.parser as parser
    monkeypatch.setattr(
        parser, "parse",
        lambda p: (_ for _ in ()).throw(OSError("truncated file: eof=15MB")))
    res = mosdac_ocm._live_chain(20.9, 70.37)
    assert res.get("value") is None
    assert not poisoned.exists()
    assert "truncated cached granule purged" in res["error"]


def test_gate_purges_poisoned_cache_and_redownloads(tmp_path, monkeypatch):
    """The REAL laptop case: parser.parse never raises, so the chain-level
    hook can't be relied on — the GATE must catch a signature-valid but
    open-failing HDF5 (eof 15 MB vs stored_eof 60.5 MB) and heal."""
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    bad = tmp_path / "mosdac_444.h5"
    bad.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 100)  # looks HDF5, won't open
    resp = _FakeResp([b"fresh-granule-bytes"])
    path, err, secs = mosdac_ocm._download_granule(_FakeSession(resp), 444)
    assert err is None
    assert path.read_bytes() == b"fresh-granule-bytes"  # healed via fresh download
    assert secs > 0  # download really happened (not a poisoned cache hit)


def test_gate_never_judges_non_hdf5_files(tmp_path, monkeypatch):
    """Churn-safety: a classic netCDF-3 (or any non-HDF5) file must NOT be
    deleted by the gate — otherwise every click would re-download."""
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    f = tmp_path / "mosdac_445.nc3"
    f.write_bytes(b"CDF\x01" + b"\x00" * 50)
    assert mosdac_ocm._cache_entry_poisoned(f) is False
    assert f.exists()


def test_gate_serves_healthy_hdf5_without_download(tmp_path, monkeypatch):
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    h5py = __import__("h5py")
    f = tmp_path / "mosdac_446.h5"
    with h5py.File(f, "w") as h:
        h.create_dataset("x", data=[1, 2, 3])

    class _Boom:
        def get(self, *a, **k):
            raise AssertionError("download called for a HEALTHY cache entry")

    path, err, secs = mosdac_ocm._download_granule(_Boom(), 446)
    assert err is None and path == f and secs == 0.0


def test_server_polite_midclose_is_rejected(tmp_path, monkeypatch):
    """If the server ENDs the stream politely at 15 MB of a 60 MB file (no
    exception), the publish-verify must catch the truncated granule."""
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    body = b"\x89HDF\r\n\x1a\n" + b"\x00" * 100  # truncated HDF5 content
    resp = _FakeResp([body])  # stream ends cleanly → no exception
    path, err, _ = mosdac_ocm._download_granule(_FakeSession(resp), 447)
    assert path is None and "truncated" in err.lower()
    assert not (tmp_path / "mosdac_447.h5").exists()


def test_download_wall_cap_aborts_slow_but_alive_stream(tmp_path, monkeypatch):
    """The 110s-deadline killer: a slow-but-STEADY connection (bytes keep
    coming, so the idle-timeout never fires) must still be aborted at the
    total wall cap — otherwise one granule download blocks the route for
    minutes (laptop inland clicks, 2026-09-04 evening).

    Since the background-drain fix, the REQUEST is still released at the
    cap, but the stream keeps trickling to completion in a daemon thread:
    the completed granule lands in the same-day cache instead of being
    thrown away (real bytes, honest messaging)."""
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    monkeypatch.setattr(mosdac_ocm, "MAX_DL_WALL_SEC", 0.08)

    class _SlowResp(_FakeResp):
        # model REAL requests semantics: a second iter_content call does
        # NOT restart — the underlying stream continues from the position
        # where the request-side loop stopped (that's what the drain needs)
        _i = 0
        def iter_content(self, size):
            import time as _t
            while self._i < len(self._chunks):
                c = self._chunks[self._i]; self._i += 1
                _t.sleep(0.01)
                yield c

    resp = _SlowResp([b"x" * 1024] * 30)  # 30 KB, drip-fed over ~0.3 s
    t0 = time.time()
    path, err, secs = mosdac_ocm._download_granule(_FakeSession(resp), 448)
    assert path is None and "too slow" in err.lower()
    assert "background" in err.lower()   # tells the user a retry will be instant
    assert time.time() - t0 < 5          # request honoured the cap, didn't hang
    # ...while the drain finished the REAL file to the same-day cache:
    t = mosdac_ocm._DRAIN_THREADS.get(448)
    assert t is not None
    t.join(timeout=15)
    assert not t.is_alive()
    dest = tmp_path / "mosdac_448.h5"
    assert dest.exists() and dest.stat().st_size == 30 * 1024
    assert not list(tmp_path.glob("*.part"))


def test_drain_keeps_part_file_safe_from_purge(tmp_path, monkeypatch):
    """A .part being completed by a live drain is NOT debris — the
    immediate-purge path must skip it or the drain's work is destroyed
    mid-write (and the drain registry must clean itself up after)."""
    monkeypatch.setattr(mosdac_ocm, "GRANULE_DIR", tmp_path)
    monkeypatch.setattr(mosdac_ocm, "MAX_DL_WALL_SEC", 0.06)

    class _SlowResp(_FakeResp):
        # model REAL requests semantics: a second iter_content call does
        # NOT restart — the underlying stream continues from the position
        # where the request-side loop stopped (that's what the drain needs)
        _i = 0
        def iter_content(self, size):
            import time as _t
            while self._i < len(self._chunks):
                c = self._chunks[self._i]; self._i += 1
                _t.sleep(0.01)
                yield c

    resp = _SlowResp([b"y" * 2048] * 40)  # 80 KB trickle
    path, err, secs = mosdac_ocm._download_granule(_FakeSession(resp), 999)
    assert path is None and "background" in err.lower()
    tmp = tmp_path / "mosdac_999.h5.part"
    assert tmp.exists()                    # interrupted file KEPT for the drain
    mosdac_ocm._purge_old_granules()       # running purge must NOT kill it
    assert tmp.exists()
    t = mosdac_ocm._DRAIN_THREADS.get(999)
    assert t is not None
    t.join(timeout=15)
    assert not t.is_alive()
    assert 999 not in mosdac_ocm._DRAIN_THREADS
    assert 999 not in mosdac_ocm._DRAIN_PATHS
    # complete file is now a same-day cache hit — no network touched
    assert not tmp.exists()
    assert (tmp_path / "mosdac_999.h5").stat().st_size == 40 * 2048
    hit, err2, secs2 = mosdac_ocm._download_granule(_FakeSession(_FakeResp([b"Z"])), 999)
    assert hit is not None and err2 is None and secs2 == 0.0


def test_failed_chain_cached_briefly_retry_not_repaid(monkeypatch, tmp_path):
    """A failed chain is cached for 10 min: repeat clicks answer instantly
    from the failure entry instead of re-paying the login→download path,
    while a transient failure does NOT stick for the 6-h success TTL."""
    calls: list[int] = []
    monkeypatch.setattr(mosdac_ocm, "mosdac_enabled", lambda: True)

    def _boom(lat, lon):
        calls.append(1)
        return {"error": "MOSDAC OCM-3 live fetch failed (download too slow)",
                "source": mosdac_ocm.SOURCE_LABEL}

    monkeypatch.setattr(mosdac_ocm, "_live_chain", _boom)
    import pipeline.ttlcache as ttlcache
    ttlcache.clear()
    r1 = mosdac_ocm.get_chlorophyll(20.9, 70.37)
    r2 = mosdac_ocm.get_chlorophyll(20.9, 70.37)
    assert len(calls) == 1                      # second click served from cache
    assert "10 min" in r1["error"]
    ent = ttlcache._store[f"mosdac_chl:{20.9:.2f},{70.37:.2f}"]
    remaining = ent[0] - time.time()
    assert 0 < remaining <= 610                 # ~10 min, NOT 6 h


def test_ttlcache_ttl_for_override(monkeypatch):
    import pipeline.ttlcache as ttlcache
    ttlcache.clear()
    v = ttlcache.cached("k1", 3600.0, lambda: {"ok": True},
                        ttl_for=lambda r: 60.0)
    ent = ttlcache._store["k1"]
    assert ent[0] - time.time() <= 65           # override won over 3600 s
    assert v == {"ok": True}


def test_records_date_from_dcdate():
    """Real apios shape seen 2026-09-04: title is the numeric id; date
    lives in dcDate/updated."""
    j = {"records": [{"id": 18352886,
                      "dcDate": "2026-09-03T10:15:00Z",
                      "updated": "2026-09-03T11:00:00Z"}]}
    recs = mosdac_ocm._records(j)
    assert recs[0]["date"] == "2026-09-03"


# ── client-side coverage filter (the Maldives-scene lesson) ────────────

def test_fail_message_never_cuts_mid_word():
    """Reviewer catch 2026-09-07: the long multi-granule failure string was
    sliced with [:180] and ended literally 'no v'. Must end at a boundary."""
    from pipeline.mosdac_ocm import _fail_message
    why = (
        "35 outside-area granule(s) skipped. "
        "18367074: no valid pixel near point [direct-reader: all fill/masked within 40 cells of point]; or "
        "18360750: no valid pixel near point [direct-reader: all fill/masked within 40 cells of point]; or "
        "18358001: no valid pixel near point"
    )
    msg = _fail_message(why)
    assert len(msg) <= 260
    assert msg.endswith(") — NOAA primary is used")
    body = msg[len("MOSDAC OCM-3 live fetch failed ("):-len(") — NOAA primary is used")]
    assert not body.endswith("no v"), msg
    assert body.endswith("+more") or body.endswith("…") or body.endswith("point]") or body.endswith("point"), msg
    # full first candidate stays intact
    assert "18367074: no valid pixel near point" in body


def test_fail_message_short_passthrough():
    from pipeline.mosdac_ocm import _fail_message
    msg = _fail_message("login failed: HTTP 401")
    assert msg == "MOSDAC OCM-3 live fetch failed (login failed: HTTP 401) — NOAA primary is used"


def test_boundbox_contains_comma_format():
    bb = "65.0,18.0,72.5,23.5"  # minLon,minLat,maxLon,maxLat
    assert mosdac_ocm._boundbox_contains(bb, 20.9, 70.37) is True
    assert mosdac_ocm._boundbox_contains(bb, 5.0, 60.0) is False
    assert mosdac_ocm._boundbox_contains("", 20.9, 70.37) is None


def test_boundbox_contains_wkt_polygon():
    bb = "POLYGON((53.4 -0.1, 68.2 -0.1, 68.2 8.3, 53.4 8.3, 53.4 -0.1))"
    assert mosdac_ocm._boundbox_contains(bb, 20.9, 70.37) is False
    assert mosdac_ocm._boundbox_contains(bb, 4.0, 60.0) is True


def test_live_chain_skips_non_covering_granules(monkeypatch):
    """The 2026-09-04 bug: search returned south-of-India scenes for a
    Veraval point. Non-covering records must be skipped BEFORE download;
    with no covering candidates the error must say so honestly."""
    monkeypatch.setenv("MOSDAC_USERNAME", "u")
    monkeypatch.setenv("MOSDAC_PASSWORD", "p")
    monkeypatch.setattr(mosdac_ocm, "_session", None)
    monkeypatch.setattr(mosdac_ocm, "_session_time", 0.0)
    monkeypatch.setattr(mosdac_auth, "login", lambda: object())
    monkeypatch.setattr(
        mosdac_auth, "search",
        lambda *a, **k: {"totalResults": 2, "records": [
            {"id": 1, "dcDate": "2026-09-04", "boundbox": "53.4,-0.1,68.2,8.3"},
            {"id": 2, "dcDate": "2026-09-03", "boundbox": "53.4,-0.1,68.2,8.3"}]})
    downloads = []
    monkeypatch.setattr(
        mosdac_ocm, "_download_granule",
        lambda s, rid: downloads.append(rid) or (None, "should-not-be-called", 0.0))
    res = mosdac_ocm._live_chain(20.9, 70.37)
    assert downloads == [], "must NOT download granules that don't cover the point"
    assert "NONE covers this point" in res["error"]


def test_login_search_over_budget_fails_with_stage_names(monkeypatch):
    """Slow-link night (2026-09-07): login+search swallowed the budget and
    the chain drifted into the download phase, where the outer 75 s job
    cap killed it facelessly ('timeout after 75s'). Now the chain stops
    AT the stage and names it, with the measured timings in the error."""
    _patch_live_world(monkeypatch, None)
    seen_dl = {"called": False}
    monkeypatch.setattr(
        mosdac_ocm, "_download_granule",
        lambda *a, **kw: seen_dl.__setitem__("called", True) or (None, "x", 0.0))
    job = mosdac_ocm.JOB_BUDGET_SEC
    clock = {"t": 1000.0}
    real_time = mosdac_ocm.time.time

    def fake_time():
        # login ~20 s, then search pushes the clock past the stage guard
        t = clock["t"]
        clock["t"] += 20.0
        return t

    monkeypatch.setattr(mosdac_ocm.time, "time", fake_time)
    try:
        # sanity: the stubbed world + one record exists so only the BUDGET
        # can be the reason to fail
        res = mosdac_ocm._live_chain(20.9, 70.37)
    finally:
        monkeypatch.setattr(mosdac_ocm.time, "time", real_time)
    assert res.get("value") is None
    assert "login" in res["error"] and "search" in res["error"], res["error"]
    assert "budget" in res["error"], res["error"]
    assert not seen_dl["called"], "download must NOT start when the stage budget is spent"
    print("✅ over-budget login+search fails at the stage, names measured timings")


def test_download_receives_remaining_budget(monkeypatch):
    """The per-candidate download must be handed what's LEFT of the job
    budget — that's what keeps the whole chain inside the outer 75 s cap."""
    _patch_live_world(monkeypatch, {"value": 0.5, "units": "mg m^-3", "distance_deg": 0.01})
    caps = {}

    def spy_dl(session, rid, **kw):
        caps.update(kw)
        return ("/tmp/fake_mosdac_granule.h5", None, 1.0)

    monkeypatch.setattr(mosdac_ocm, "_download_granule", spy_dl)
    res = mosdac_ocm._live_chain(20.9, 70.37)
    assert res["value"] == 0.5
    assert "wall_cap_sec" in caps and "idle_cap_sec" in caps, caps
    assert 5.0 <= caps["wall_cap_sec"] <= mosdac_ocm.MAX_DL_WALL_SEC
    assert caps["idle_cap_sec"] <= caps["wall_cap_sec"] + 38  # idle = min(45, wall)
    print(f"✅ download bounded by remaining budget (wall {caps['wall_cap_sec']:.0f}s)")
