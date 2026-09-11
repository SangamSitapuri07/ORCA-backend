"""ORCA Live Beacon — "Samudri Rakshak Net" (B18).

Idea (product owner): AIS waale ships har 2–10 second mein apni position
VHF radio pe broadcast karti hain — isi liye GFW unhe track kar paata hai.
Toh hamare fishermen ke PHONE ko bhi waise hi ek transponder bana do:

  • voyage start → phone har ~30 s mein ek chhota GPS ping bhejta hai
    (~100 bytes — 2G/edge signal pe bhi chal jaata hai)
  • backend ek LIVE TRAIL rakhta hai (AIS jaisa), anonymous session se
  • SOS dabaya → beacon RED → DEFAULT_RADIUS_NM ke andar ke saare ORCA
    boats agle apne ping ke response mein hi alert pa jaate hain
    (ALAG se polling ki zaroorat hi nahi — ping khud alert-channel hai)
  • family / rescue team ko shareable public-id link se live position
    milti hai

PRIVACY BY DESIGN (AIS broadcast philosophy, fisher ke CONTROL mein):
  • position sirf tab store hoti hai jab USER khud beacon ON rakhe
    (jaise ship ka AIS — vo bhi jaanke broadcast karta hai)
  • koi login, naam, device id, phone number — KUCH nahi; session ek
    random id hai, aur public responses mein raw session KABHI nahi
    jaata (sirf 8-char sha256 pub_id)
  • PING_MAX_AGE_SEC (default 2 h) tak koi ping nahi → record AUTO-DELETE
  • SOS bhi SOS_MAX_AGE_SEC (12 h) se zyada kabhi zinda nahi rehta
  • /live/stop → turant poora delete

Judges ko bolne layak line: "GFW/AIS duniya ko lines dikhata hai;
ORCA lines se ACTION loop banata hai — plan → track → alert → rescue.
Fishermen rescuing fishermen — coast guard 1–3 ghante mein pahunchta
hai, paas wala ORCA boat 20 minute mein."

Persistence: atomic JSON store (env ORCA_LIVE_STORE) — restart ke baad
bhi active beacons wapas aa jaate hain (demo safety), expired auto-prune.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import tempfile
import threading
import time
from typing import Any

# ── tunables (har number judge ke saamne auditable) ─────────────────
PING_MAX_AGE_SEC = 2 * 3600      # 2 h silence → boat auto-delete (privacy)
SOS_MAX_AGE_SEC = 12 * 3600      # SOS kabhi bhi 12 h se zyada nahi rehta
DEFAULT_RADIUS_NM = 20.0         # "paas ke boats" / SOS alert radius
MAX_RADIUS_NM = 100.0
MAX_BOATS = 2000                 # sabse purane (non-SOS) ko evict karo
NM_PER_KM = 1 / 1.852
EARTH_R_KM = 6371.0088

_lock = threading.Lock()
_boats: dict[str, dict[str, Any]] = {}
_loaded = False


def _store_path() -> str:
    return os.environ.get("ORCA_LIVE_STORE") or os.path.join(
        os.path.expanduser("~"), ".orca_live_store.json")


def reset() -> None:
    """Sab kuch saaf (tests / ops). File agle write pe prune ho jaati hai."""
    global _loaded
    with _lock:
        _boats.clear()
        _loaded = True


def new_session() -> str:
    return secrets.token_hex(8)


def pub_id(session: str) -> str:
    """Anonymous public id — RAW session id server se bahar kabhi nahi jaati."""
    return hashlib.sha256(session.encode("utf-8")).hexdigest()[:8]


# ── geo helpers (self-contained — voyage/routeadvisory se independent) ──

def _haversine_nm(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(h))) * NM_PER_KM


def _bearing_deg(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dl = math.radians(b_lon - a_lon)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


# ── internals ────────────────────────────────────────────────────────

def _valid_coord(lat: Any, lon: Any) -> bool:
    return (
        isinstance(lat, (int, float)) and not isinstance(lat, bool)
        and isinstance(lon, (int, float)) and not isinstance(lon, bool)
        and -90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0
    )


def _prune_locked(now: float) -> None:
    dead = []
    for s, b in _boats.items():
        ts = float(b.get("ts", 0.0))
        if now - ts > PING_MAX_AGE_SEC:
            dead.append(s)  # voyage khatam / phone dead → privacy delete
        elif b.get("sos") and now - float(b.get("sos_ts", ts)) > SOS_MAX_AGE_SEC:
            dead.append(s)  # 12 h purana SOS bhi nahi rakhte
    for s in dead:
        _boats.pop(s, None)


def _load_locked() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(_store_path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        for s, b in (raw.get("boats") or {}).items():
            if isinstance(s, str) and isinstance(b, dict) and _valid_coord(b.get("lat"), b.get("lon")):
                _boats[s] = b
        _prune_locked(time.time())
    except Exception:  # noqa: BLE001 — rescue net kabhi bad file pe crash nahi
        pass


def _save_locked() -> None:
    path = _store_path()
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".live_", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"saved_at": time.time(), "boats": _boats}, fh)
        os.replace(tmp, path)  # atomic — crash ke beech bhi poorani file safe
    except Exception:  # noqa: BLE001
        pass


def _evict_locked() -> None:
    """Store full ho toh sabse PURANI non-SOS boat hatao (SOS kabhi evict nahi)."""
    while len(_boats) > MAX_BOATS:
        victims = [(float(b.get("ts", 0.0)), s) for s, b in _boats.items() if not b.get("sos")]
        if not victims:
            break
        victims.sort()
        _boats.pop(victims[0][1], None)


def _public(session: str, b: dict[str, Any], now: float,
            viewer: tuple[float, float] | None = None) -> dict[str, Any]:
    """Public projection — raw session id KABHI include nahi hoti."""
    out: dict[str, Any] = {
        "pub_id": pub_id(session),
        "lat": round(float(b["lat"]), 5),
        "lon": round(float(b["lon"]), 5),
        "age_sec": max(0, int(now - float(b["ts"]))),
        "sos": bool(b.get("sos")),
    }
    if b.get("label"):
        out["label"] = str(b["label"])[:40]
    if b.get("speed_kn") is not None:
        out["speed_kn"] = round(float(b["speed_kn"]), 1)
    if b.get("heading_deg") is not None:
        out["heading_deg"] = int(round(float(b["heading_deg"]))) % 360
    if out["sos"]:
        out["sos_age_sec"] = max(0, int(now - float(b.get("sos_ts", b["ts"]))))
        if b.get("sos_note"):
            out["sos_note"] = str(b["sos_note"])[:140]
    if viewer is not None:
        out["distance_nm"] = round(
            _haversine_nm(viewer[0], viewer[1], float(b["lat"]), float(b["lon"])), 2)
        out["bearing_deg"] = int(round(
            _bearing_deg(viewer[0], viewer[1], float(b["lat"]), float(b["lon"]))))
    return out


# ── public API ───────────────────────────────────────────────────────

def start(session: str, lat: float, lon: float, label: str | None = None,
          ts: float | None = None, now: float | None = None) -> dict[str, Any]:
    """Beacon ON. Session client bana sakta hai ya server se le sakta hai."""
    now = time.time() if now is None else now
    if not session:
        session = new_session()
    with _lock:
        _load_locked()
        _prune_locked(now)
        created = session not in _boats
        _boats[session] = {
            "lat": float(lat), "lon": float(lon), "ts": ts if ts is not None else now,
            "label": (str(label).strip()[:40] or None) if label else None,
            "sos": False,
        }
        _evict_locked()
        _save_locked()
    return {"ok": True, "created": created, "session": session, "pub_id": pub_id(session)}


def ping(session: str, lat: float, lon: float, speed_kn: float | None = None,
         heading_deg: float | None = None, label: str | None = None,
         ts: float | None = None, now: float | None = None) -> dict[str, Any]:
    """Heartbeat + position update. RESPONSE mein hi paas ke SOS aa jaate
    hain — sailing mode mein alag polling ki zaroorat hi nahi."""
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        created = False
        if session not in _boats:
            created = True
            # phone restart / app crash ke baad bhi flow kabhi nahi tootta
            _boats[session] = {"sos": False, "label": None}
        b = _boats[session]
        b["lat"], b["lon"] = float(lat), float(lon)
        b["ts"] = ts if ts is not None else now
        if speed_kn is not None:
            b["speed_kn"] = float(speed_kn)
        if heading_deg is not None:
            b["heading_deg"] = float(heading_deg) % 360.0
        if label:
            b["label"] = str(label).strip()[:40] or None
        _evict_locked()
        _save_locked()
        alerts = [
            _public(s, ob, now, viewer=(float(lat), float(lon)))
            for s, ob in _boats.items()
            if ob.get("sos") and s != session
            and _haversine_nm(float(lat), float(lon), float(ob["lat"]), float(ob["lon"]))
            <= DEFAULT_RADIUS_NM
        ]
        alerts.sort(key=lambda x: x["distance_nm"])
    return {"ok": True, "created": created, "pub_id": pub_id(session),
            "sos_nearby": alerts, "sos_nearby_count": len(alerts)}


def sos_on(session: str, note: str | None = None, lat: float | None = None,
           lon: float | None = None, ts: float | None = None,
           now: float | None = None) -> dict[str, Any]:
    """Beacon RED. Unknown session ke liye lat/lon do toh register karke
    SOS shuru karenge — SOS flow mein NAHI, 'pehle start karo' error
    kabhi zindagi-maut ke waqt nahi aana chahiye."""
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        if session not in _boats:
            if lat is None or lon is None or not _valid_coord(lat, lon):
                return {"ok": False,
                        "error": "unknown session — pehle /live/start ya lat/lon ke saath SOS"}
            _boats[session] = {"lat": float(lat), "lon": float(lon),
                               "ts": now, "label": None}
        b = _boats[session]
        if lat is not None and lon is not None and _valid_coord(lat, lon):
            b["lat"], b["lon"] = float(lat), float(lon)
        b["sos"] = True
        b["sos_ts"] = ts if ts is not None else now
        if note:
            b["sos_note"] = str(note).strip()[:140] or None
        _save_locked()
        pub = _public(session, b, now)
    return {"ok": True, "sos": True, **pub}


def sos_off(session: str, now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        b = _boats.get(session)
        if not b:
            return {"ok": False, "error": "unknown session"}
        b["sos"] = False
        b.pop("sos_ts", None)
        b.pop("sos_note", None)
        _save_locked()
    return {"ok": True, "sos": False, "pub_id": pub_id(session)}


def stop(session: str, now: float | None = None) -> dict[str, Any]:
    """Beacon OFF = POORA delete. Privacy promise: OFF ka matlab OFF."""
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        existed = session in _boats
        _boats.pop(session, None)
        _save_locked()
    return {"ok": True, "deleted": existed}


def nearby(lat: float, lon: float, radius_nm: float = DEFAULT_RADIUS_NM,
           now: float | None = None) -> dict[str, Any]:
    """Radius ke andar ke saare live beacons — distance + bearing ke saath."""
    now = time.time() if now is None else now
    radius_nm = max(0.5, min(MAX_RADIUS_NM, float(radius_nm)))
    with _lock:
        _load_locked()
        _prune_locked(now)
        viewer = (float(lat), float(lon))
        out = []
        for s, b in _boats.items():
            d = _haversine_nm(float(lat), float(lon), float(b["lat"]), float(b["lon"]))
            if d <= radius_nm:
                out.append(_public(s, b, now, viewer=viewer))
        out.sort(key=lambda x: x["distance_nm"])
    return {
        "center": {"lat": float(lat), "lon": float(lon)},
        "radius_nm": radius_nm,
        "boats": out,
        "count": len(out),
        "sos_count": sum(1 for x in out if x["sos"]),
        "generated_at": int(now),
    }


def sos_list(now: float | None = None) -> dict[str, Any]:
    """Poore network ke active SOS — command-center view ke liye."""
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        out = [_public(s, b, now) for s, b in _boats.items() if b.get("sos")]
        out.sort(key=lambda x: x["sos_age_sec"])
    return {"sos": out, "count": len(out), "generated_at": int(now)}


def by_pub_id(pid: str, now: float | None = None) -> dict[str, Any] | None:
    """Share-link lookup — family/rescue team sirf pub_id jaanti hai,
    raw session kabhi nahi. None = unknown/expired/stopped."""
    now = time.time() if now is None else now
    pid = str(pid).strip().lower()
    if not pid:
        return None
    with _lock:
        _load_locked()
        _prune_locked(now)
        for s, b in _boats.items():
            if pub_id(s) == pid:
                return _public(s, b, now)
    return None


def stats(now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        ages = [now - float(b.get("ts", now)) for b in _boats.values()]
    return {
        "active_boats": len(_boats),
        "sos_active": sum(1 for b in _boats.values() if b.get("sos")),
        "oldest_ping_age_sec": int(max(ages)) if ages else 0,
        "auto_delete_after_sec": PING_MAX_AGE_SEC,
        "sos_max_age_sec": SOS_MAX_AGE_SEC,
        "default_radius_nm": DEFAULT_RADIUS_NM,
        "privacy": ("no login/identity · raw session id never leaves the server · "
                    "positions stored ONLY while the fisher keeps the beacon on · "
                    "auto-delete after 2 h of silence · /live/stop deletes instantly"),
        "model": "AIS-style broadcast — same philosophy as ship transponders, for fisherfolk phones",
    }
