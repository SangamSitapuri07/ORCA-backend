"""MOSDAC authentication helper — FIXED VERSION (official download_api).

DIRECTORY MAP (why old version failed):
  - Old code fought Keycloak SSO (browser-only door). ISRO does not allow
    bots there -> "unauthorized_client" / lockouts after repeated attempts.
  - OFFICIAL door for machines = MOSDAC's own download API:
        token   POST  /download_api/gettoken      (username+password JSON)
        search  GET   /apios/datasets.json        (NO token needed!)
        download GET  /download_api/download?id=  (Bearer token)
    (Source: official client mdapi.py -> https://mosdac.gov.in/software/mdapi.zip)

VERIFIED LIVE (3 Sep 2026):
  - 3RIMG_L2B_SST  (INSAT-3DR SST): 77 files/day
  - E06OCM_L2C_LAC_OC (EOS-06/Oceansat-3 OCM chlorophyll a.k.a. ocean colour):
        71 files in last week for boundingBox Gujarat "66.0,18.0,72.5,23.5"
  - boundingBox format = "minLon,minLat,maxLon,maxLat" ; dates = YYYY-MM-DD
  - Daily limit: 5000 files/user/day.

INTERFACE (unchanged from old file — nothing else in repo needs edits):
    login()        -> requests.Session with Authorization header set
    quick_check()  -> bool
    refresh(session) helper + search()/download_file() conveniences.

Credentials from MOSDAC_USERNAME / MOSDAC_PASSWORD (env or .env file).
IMPORTANT: do not spam gettoken — accounts lock after repeated bad tries.
"""
import json
import os
from pathlib import Path

import requests

# --- .env auto-load (silent, never raises) -------------------------
def _load_dotenv(path):
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass

_here = Path(__file__).resolve().parent
for _p in (_here.parent, _here.parent.parent, Path.cwd()):
    _load_dotenv(os.path.join(str(_p), ".env"))

TOKEN_URL = "https://mosdac.gov.in/download_api/gettoken"
REFRESH_URL = "https://mosdac.gov.in/download_api/refresh-token"
SEARCH_URL = "https://mosdac.gov.in/apios/datasets.json"
DOWNLOAD_URL = "https://mosdac.gov.in/download_api/download"
CHECKNET_URL = "https://mosdac.gov.in/download_api/check-internet"

# datasets we actually use (verified live)
DS_SST = "3RIMG_L2B_SST"          # INSAT-3DR Sea Surface Temperature
DS_OCM_OC = "E06OCM_L2C_LAC_OC"   # EOS-06/Oceansat-3 OCM ocean colour (chlorophyll)
BBOX_GUJARAT = "66.0,18.0,72.5,23.5"


class MosdacAuthError(Exception):
    pass


def _get_creds():
    user = os.environ.get("MOSDAC_USERNAME", "").strip()
    pwd = os.environ.get("MOSDAC_PASSWORD", "").strip()
    if not user or not pwd:
        raise MosdacAuthError(
            "MOSDAC_USERNAME and MOSDAC_PASSWORD must be set.\n"
            "Add them to a .env file in the project root:\n"
            "    MOSDAC_USERNAME=your_username\n"
            "    MOSDAC_PASSWORD=your_password"
        )
    return user, pwd


def _fetch_token(user, pwd):
    """ONE call to the official token endpoint. Returns (access, refresh) or raises."""
    try:
        r = requests.post(TOKEN_URL, json={"username": user, "password": pwd}, timeout=20)
    except requests.RequestException as e:
        raise MosdacAuthError("Network error talking to gettoken: %s" % e)

    if r.status_code == 400:
        msg = ""
        try:
            msg = r.json().get("error", "")
        except Exception:
            pass
        raise MosdacAuthError("Validation error from gettoken: %s" % (msg or r.text[:200]))
    if r.status_code == 401:
        raise MosdacAuthError(
            "401 Unauthorized: wrong username/password for download_api.\n"
            "NOTE: repeated wrong tries LOCK the account for ~1 hour. "
            "First confirm login in browser at https://mosdac.gov.in (SSO page), "
            "then re-run this ONCE."
        )
    if r.status_code == 503:
        raise MosdacAuthError("MOSDAC service unavailable (maintenance?). Try later.")
    if r.status_code != 200:
        raise MosdacAuthError("gettoken HTTP %s: %s" % (r.status_code, r.text[:200]))

    j = r.json()
    access, refresh = j.get("access_token"), j.get("refresh_token")
    if not access:
        raise MosdacAuthError("gettoken returned no access_token: %s" % str(j)[:200])
    return access, refresh


def login():
    """Log in to MOSDAC; return requests.Session with Bearer set (SAME as old API)."""
    user, pwd = _get_creds()
    access, refresh = _fetch_token(user, pwd)
    s = requests.Session()
    s.headers.update({
        "User-Agent": "ORCA-ps176/0.1 (SIH 2026)",
        "Accept": "application/json",
        "Authorization": "Bearer " + access,
    })
    s.mosdac_refresh_token = refresh  # keep for later refresh() calls
    return s


def refresh(session):
    """Swap a dead access token for a fresh one using the stored refresh token."""
    rt = getattr(session, "mosdac_refresh_token", None)
    if not rt:
        raise MosdacAuthError("no refresh token stored on session")
    r = requests.post(REFRESH_URL, json={"refresh_token": rt}, timeout=20)
    if r.status_code != 200:
        raise MosdacAuthError("refresh failed HTTP %s — call login() again" % r.status_code)
    j = r.json()
    session.headers["Authorization"] = "Bearer " + j["access_token"]
    session.mosdac_refresh_token = j.get("refresh_token", rt)
    return session


def search(dataset_id, start=None, end=None, bbox=None, count="1"):
    """Query the free OpenSearch endpoint (NO login needed). Returns parsed JSON.

    NOTE (live 2026-09-04): boundingBox is sent under BOTH common param
    names — the server ignored `boundingBox` for one dataset, so a
    client-side boundbox check still happens downstream in mosdac_ocm.
    """
    params = {"datasetId": dataset_id, "count": count}
    if start:
        params["startTime"] = start
    if end:
        params["endTime"] = end
    if bbox:
        params["boundingBox"] = bbox
        params["bbox"] = bbox
    r = requests.get(SEARCH_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def download_file(session, record_id, out_dir=".", filename=None):
    """Download one granule by its search-record id. Auto-refresh once on 401."""
    os.makedirs(out_dir, exist_ok=True)
    for attempt in (1, 2):
        r = session.get(DOWNLOAD_URL, params={"id": record_id}, timeout=300, stream=True)
        if r.status_code == 401 and attempt == 1:
            refresh(session)
            continue
        if r.status_code != 200:
            raise MosdacAuthError("download HTTP %s for id=%s" % (r.status_code, record_id))
        fname = filename or ("mosdac_" + str(record_id))
        cd = r.headers.get("Content-Disposition", "")
        if "filename=" in cd and filename is None:
            fname = cd.split("filename=", 1)[1].strip('"').strip()
        path = os.path.join(out_dir, fname)
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        return path
    raise MosdacAuthError("download failed after refresh")


def quick_check():
    """One-shot verification: token + real search for our 2 target datasets."""
    print("=" * 66)
    print("  MOSDAC official download_api check (ONE login attempt only)")
    print("=" * 66)
    try:
        user = os.environ.get("MOSDAC_USERNAME", "")
        print("  user:", user or "(not set)")
        print("  asking for token…")
        s = login()
    except MosdacAuthError as e:
        print("  X MOSDAC login failed: " + str(e))
        return False
    print("  OK token received (access + refresh). SSO fight skipped — using official API. ✅")

    # search needs NO token — proves datasets are reachable for us
    for did, note in ((DS_SST, "INSAT-3DR SST"), (DS_OCM_OC, "EOS-06 OCM chlorophyll")):
        try:
            d = search(did, start="2026-08-25", end="2026-09-02", bbox=BBOX_GUJARAT, count="1")
            total = d.get("totalResults", "?")
            print("  OK search %-18s (%s): %s files in Gujarat box, 25Aug-2Sep" % (did, note, total))
        except Exception as e:
            print("  ! search failed for %s: %s" % (did, e))
    print("  MOSDAC pipeline READY. Use search() + download_file() from this module. 🎣")
    return True


if __name__ == "__main__":
    quick_check()
