"""ORCA Live Beacon — "Samudri Rakshak Net" (B18 base + B19 rescue dispatch).

Idea (product owner): AIS waale ships har 2–10 second mein apni position
VHF radio pe broadcast karti hain — isi liye GFW unhe track paata hai.
Toh hamare fishermen ke PHONE ko bhi waise hi ek transponder bana do:

  • voyage start → phone har ~30 s mein ek chhota GPS ping bhejta hai
    (~100 bytes — 2G/edge signal pe bhi chal jaata hai)
  • backend ek LIVE TRAIL rakhta hai (AIS jaisa), anonymous session se
  • SOS dabaya → beacon RED → RESCUE DISPATCH (B19):

B19 — real maritime SAR workflow ka digital roop (MRCC = Maritime
Rescue Coordination Centre ka standard flow):
    1. MAYDAY     → fisher 1-tap SOS (kuch type/copy nahi — link-copy
                    workflow galat tha, banda paani mein hai)
    2. TRACE      → BACKEND KHUD nearest live beacons dhoondhta hai
                    (haversine, escalating tiers 10 → 25 → 50 NM)
    3. MAYDAY RELAY → un boats ke AGLE ping ke response mein hi
                    RESCUE REQUEST ghush jaata hai (accept/decline)
                    — alag polling / push server ki zaroorat hi nahi
    4. ACK        → rescuer "MADAD KARUNGA" → dono taraf live tracking:
                    victim dekhta hai "RescueOne aa raha hai · 1.7 NM ·
                    ETA ~17 min", rescuer ko milte hai bearing/doori
                    (jo har ping pe taaza hoti hai — real approach)
    5. ESCALATION → 60 s mein koi accept nahi → tier badhao, aur door
                    ke boats ko request (judged demo ke liye visible)
    6. RESOLVE    → victim "main theek hoon" ya rescuer "pahunch gaya"
                    → case close → privacy wipe

PRIVACY BY DESIGN (AIS broadcast philosophy, fisher ke CONTROL mein):
  • position sirf tab store hoti hai jab USER khud beacon ON rakhe
  • koi login/naam/device id/phone number — random session id; public
    responses mein raw session KABHI nahi (8-char sha256 pub_id)
  • PING_MAX_AGE_SEC (2 h) silence → record AUTO-DELETE
  • SOS ≤ SOS_MAX_AGE_SEC (12 h); /live/stop → turant poora delete
  • case_id unguessable (token_hex) — sirf involved parties ko milta hai

Persistence: atomic JSON store (env ORCA_LIVE_STORE) — restart ke baad
bhi active beacons+cases restore (demo safety), expired auto-prune.
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
DEFAULT_RADIUS_NM = 20.0         # "paas ke boats" radar default
MAX_RADIUS_NM = 100.0
MAX_BOATS = 2000                 # sabse purane (non-SOS) ko evict karo
# ── B19 dispatch ──
DISPATCH_TIERS_NM = (10.0, 25.0, 50.0)   # escalation radii (MRCC style)
DISPATCH_MAX_BOATS = 5                    # ek tier mein max kitni requests
ESCALATE_AFTER_SEC = 60.0                 # no-accept → next tier
OFFER_TTL_SEC = 10 * 60                   # ek request kitni der tak khuli
NM_PER_KM = 1 / 1.852
EARTH_R_KM = 6371.0088

_lock = threading.Lock()
_boats: dict[str, dict[str, Any]] = {}
_cases: dict[str, dict[str, Any]] = {}
_loaded = False


def _store_path() -> str:
    return os.environ.get("ORCA_LIVE_STORE") or os.path.join(
        os.path.expanduser("~"), ".orca_live_store.json")


def reset() -> None:
    """Sab kuch saaf (tests / ops). File agle write pe prune ho jaati hai."""
    global _loaded
    with _lock:
        _boats.clear()
        _cases.clear()
        _loaded = True


def new_session() -> str:
    return secrets.token_hex(8)


def pub_id(session: str) -> str:
    """Anonymous public id — RAW session id server se bahar kabhi nahi jaati."""
    return hashlib.sha256(session.encode("utf-8")).hexdigest()[:8]


# ── geo helpers (self-contained) ─────────────────────────────────────

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


def _dist_brg(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, int]:
    return (
        round(_haversine_nm(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"])), 2),
        int(round(_bearing_deg(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"])))),
    )


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
            dead.append(s)
        elif b.get("sos") and now - float(b.get("sos_ts", ts)) > SOS_MAX_AGE_SEC:
            dead.append(s)
    for s in dead:
        b = _boats.pop(s, None)
        if b and b.get("sos"):
            c = _open_case_for_locked(s)
            if c:
                c["status"] = "resolved"
                c["resolved_ts"] = now
                c["resolved_by"] = "expired"
    # purane cases: resolved > 1 h ya SOS_MAX_AGE se aage — kachra saaf
    for cid, c in list(_cases.items()):
        if c.get("status") == "resolved":
            if now - float(c.get("resolved_ts", c.get("ts", 0))) > 3600:
                _cases.pop(cid, None)
        elif now - float(c.get("ts", 0)) > SOS_MAX_AGE_SEC:
            _cases.pop(cid, None)


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
        for cid, c in (raw.get("cases") or {}).items():
            if isinstance(cid, str) and isinstance(c, dict) and c.get("victim") in _boats:
                _cases[cid] = c
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
            json.dump({"saved_at": time.time(), "boats": _boats, "cases": _cases}, fh)
        os.replace(tmp, path)  # atomic
    except Exception:  # noqa: BLE001
        pass


def _evict_locked() -> None:
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
    if _accepted_rescue_case(session) is not None:
        out["on_rescue"] = True  # "madad mein ja raha" badge (social proof)
    if viewer is not None:
        out["distance_nm"] = round(
            _haversine_nm(viewer[0], viewer[1], float(b["lat"]), float(b["lon"])), 2)
        out["bearing_deg"] = int(round(
            _bearing_deg(viewer[0], viewer[1], float(b["lat"]), float(b["lon"]))))
    return out


# ── B19: rescue case machinery ───────────────────────────────────────

def _open_case_for_locked(victim_session: str) -> dict[str, Any] | None:
    for c in _cases.values():
        if c.get("victim") == victim_session and c.get("status") in ("open", "assigned"):
            return c
    return None


def _recent_case_for_locked(victim_session: str, now: float,
                            window: float = 300.0) -> dict[str, Any] | None:
    """Open case, warna abhi-abhi (5 min ke andar) resolve hua — taaki
    victim ke agle ping mein 'rescue ho gaya' ki khabar chali jaaye."""
    c = _open_case_for_locked(victim_session)
    if c:
        return c
    for c in _cases.values():
        if (c.get("victim") == victim_session and c.get("status") == "resolved"
                and now - float(c.get("resolved_ts", now)) <= window):
            return c
    return None


def _accepted_rescue_case(rescuer_session: str) -> dict[str, Any] | None:
    for c in _cases.values():
        if c.get("status") in ("open", "assigned"):
            off = (c.get("offers") or {}).get(rescuer_session)
            if off and off.get("state") == "accepted":
                return c
    return None


def _dispatch_locked(case: dict[str, Any], now: float) -> None:
    """Current tier ke andar ke NEAREST boats ko rescue request do.
    Declined/expired ko dobara nahi chedte — marzi unki."""
    victim = _boats.get(case["victim"])
    if not victim:
        return
    tier = DISPATCH_TIERS_NM[min(case.get("tier_idx", 0), len(DISPATCH_TIERS_NM) - 1)]
    offers = case.setdefault("offers", {})
    # offers referencing dead boats saaf karo
    for s in list(offers):
        if s not in _boats:
            offers.pop(s, None)
    candidates: list[tuple[float, str]] = []
    for s, b in _boats.items():
        if s == case["victim"]:
            continue
        if offers.get(s, {}).get("state") in ("declined", "expired", "accepted"):
            continue
        d, _ = _dist_brg(victim, b)
        if d <= tier:
            candidates.append((d, s))
    candidates.sort()
    room = DISPATCH_MAX_BOATS - sum(1 for o in offers.values() if o.get("state") in ("pending", "seen", "accepted"))
    for _, s in candidates[:max(0, room)]:
        if s not in offers:
            offers[s] = {"state": "pending", "ts": now, "answered_ts": None, "reason": None}
        # already pending → wapas se pending (retry allowed) — ts refresh nahi
    case["last_dispatch_ts"] = now


def _escalate_locked(now: float) -> None:
    """Koi accept nahi + ESCALATE_AFTER_SEC guzar gaye → tier badhao."""
    for c in _cases.values():
        if c.get("status") != "open":
            continue
        if any(o.get("state") == "accepted" for o in (c.get("offers") or {}).values()):
            c["status"] = "assigned"
            continue
        if c.get("tier_idx", 0) >= len(DISPATCH_TIERS_NM) - 1:
            continue
        if now - float(c.get("last_dispatch_ts", c.get("ts", 0))) >= ESCALATE_AFTER_SEC:
            c["tier_idx"] = int(c.get("tier_idx", 0)) + 1
            # teir badhi — officers dobara expire hoke bhi eligible nahi;
            # declined ko chhod ke naye boats dispatch
            _dispatch_locked(c, now)


def _expire_offers_locked(now: float) -> None:
    for c in _cases.values():
        if c.get("status") not in ("open", "assigned"):
            continue
        for o in (c.get("offers") or {}).values():
            if o.get("state") in ("pending", "seen") and now - float(o.get("ts", now)) > OFFER_TTL_SEC:
                o["state"] = "expired"


def _rescue_payload_locked(session: str, now: float) -> dict[str, Any] | None:
    """AGAR is boat ko kisi open case ki request hai → ping response mein
    jaane waala payload (accept/decline + accepted ke baad guidance)."""
    best = None
    for c in _cases.values():
        if c.get("status") not in ("open", "assigned"):
            continue
        off = (c.get("offers") or {}).get(session)
        if not off or off.get("state") in ("declined", "expired"):
            continue
        victim = _boats.get(c["victim"])
        me = _boats.get(session)
        if not victim or not me:
            continue
        if off.get("state") == "pending":
            off["state"] = "seen"  # victim honest dekhega: "itne ne DEKHA"
        d, brg = _dist_brg(me, victim)  # rescuer → victim direction
        payload = {
            "case_id": c["case_id"],
            "my_state": off["state"],
            "victim": _public(c["victim"], victim, now),
            "distance_nm": d,
            "bearing_deg": brg,
            "offer_age_sec": max(0, int(now - float(off["ts"]))),
            "expires_in_sec": max(0, int(OFFER_TTL_SEC - (now - float(off["ts"])))),
        }
        if best is None or d < best["distance_nm"]:
            best = payload
    return best


def _victim_case_payload_locked(case: dict[str, Any], now: float) -> dict[str, Any] | None:
    """Victim ke ping mein jaata hai: kisko request gayi, kisne dekha,
    kaun aa raha hai (live dist/bearing/ETA har ping pe taaza)."""
    victim = _boats.get(case["victim"])
    if not victim:
        return None
    offers = case.get("offers") or {}
    accepted: list[dict[str, Any]] = []
    for s, o in offers.items():
        if o.get("state") != "accepted":
            continue
        b = _boats.get(s)
        if not b:
            continue
        d, brg = _dist_brg(victim, b)  # victim → rescuer
        item: dict[str, Any] = {
            "pub_id": pub_id(s),
            "distance_nm": d,
            "bearing_deg": brg,
            "age_sec": max(0, int(now - float(b["ts"]))),
        }
        if b.get("label"):
            item["label"] = str(b["label"])[:40]
        sp = b.get("speed_kn")
        if isinstance(sp, (int, float)) and float(sp) >= 2.0:
            item["eta_min"] = round(d / float(sp) * 60.0)  # honest: sirf tab jab real speed ho
        else:
            item["eta_min"] = None  # speed unknown → kabhi ETA invent nahi
        accepted.append(item)
    accepted.sort(key=lambda x: x["distance_nm"])
    tier = DISPATCH_TIERS_NM[min(case.get("tier_idx", 0), len(DISPATCH_TIERS_NM) - 1)]
    return {
        "case_id": case["case_id"],
        "status": case.get("status", "open"),
        "tier_nm": tier,
        "tiers_nm": list(DISPATCH_TIERS_NM),
        "case_age_sec": max(0, int(now - float(case.get("ts", now)))),
        "escalate_in_sec": (None if case.get("status") != "open" or case.get("tier_idx", 0) >= len(DISPATCH_TIERS_NM) - 1
                            else max(0, int(ESCALATE_AFTER_SEC - (now - float(case.get("last_dispatch_ts", case.get("ts", now))))))),
        "dispatched": sum(1 for o in offers.values() if o.get("state") in ("pending", "seen", "accepted")),
        "seen": sum(1 for o in offers.values() if o.get("state") in ("seen", "accepted")),
        "declined": sum(1 for o in offers.values() if o.get("state") == "declined"),
        "expired": sum(1 for o in offers.values() if o.get("state") == "expired"),
        "accepted": accepted,
    }


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
    """Heartbeat + position update. RESPONSE hi alert channel hai:
       • sos_nearby — legacy passive list (radar fallback)
       • rescue_request — mujh pe aayi hui RESCUE REQUEST (B19)
       • my_sos — mere SOS ka dispatch status (B19): kisko gayi, kisne
         dekha, kaun aa raha hai (live dist/ETA har ping pe taaza)"""
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        created = False
        if session not in _boats:
            created = True
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
        _expire_offers_locked(now)
        _escalate_locked(now)
        alerts = [
            _public(s, ob, now, viewer=(float(lat), float(lon)))
            for s, ob in _boats.items()
            if ob.get("sos") and s != session
            and _haversine_nm(float(lat), float(lon), float(ob["lat"]), float(ob["lon"]))
            <= DEFAULT_RADIUS_NM
        ]
        alerts.sort(key=lambda x: x["distance_nm"])
        rescue_req = _rescue_payload_locked(session, now)
        my_case = _recent_case_for_locked(session, now)
        my_sos = None
        if (my_case and my_case.get("status") in ("open", "assigned")
                and b.get("sos")):
            my_sos = _victim_case_payload_locked(my_case, now)
        _save_locked()
    out: dict[str, Any] = {"ok": True, "created": created, "pub_id": pub_id(session),
                           "sos_nearby": alerts, "sos_nearby_count": len(alerts),
                           "rescue_request": rescue_req, "my_sos": my_sos}
    if my_case and my_case.get("status") == "resolved":
        rb = my_case.get("resolved_by")
        # apne khud ke clear pe dobara mat batao — sirf rescuer/third-party
        # resolution ki khabar do (victim ka SOS flag bhi is waqt cleared hai)
        if rb and rb not in (session, "expired"):
            out["sos_resolved"] = {
                "by": "rescuer" if rb != "victim_stopped" else "victim",
                "case_id": my_case["case_id"],
            }
    return out


def sos_on(session: str, note: str | None = None, lat: float | None = None,
           lon: float | None = None, ts: float | None = None,
           now: float | None = None) -> dict[str, Any]:
    """🚨 Beacon RED + AUTO-DISPATCH (B19): backend KHUD nearest boats
    trace karke unhe rescue request bhejta hai — victim ko kuch nahi karna.
    Unknown session + lat/lon → register karke SOS (zindagi-maut flow)."""
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
        first_time = not b.get("sos")
        b["sos"] = True
        b["sos_ts"] = ts if ts is not None else now
        if note:
            b["sos_note"] = str(note).strip()[:140] or None
        case = _open_case_for_locked(session)
        if case is None:
            case = {
                "case_id": secrets.token_hex(6),
                "victim": session,
                "ts": ts if ts is not None else now,
                "tier_idx": 0,
                "status": "open",
                "resolved_ts": None,
                "resolved_by": None,
                "offers": {},
            }
            _cases[case["case_id"]] = case
        # sos dobara dabaya → redispatch mat karo sirf status do (idempotent)
        if first_time or not case.get("offers"):
            _dispatch_locked(case, now)
        _save_locked()
        pub = _public(session, b, now)
        victim_view = _victim_case_payload_locked(case, now)
    return {"ok": True, "sos": True, **pub, "case": victim_view}


def sos_off(session: str, now: float | None = None) -> dict[str, Any]:
    """'Main theek hoon' → SOS band + open case RESOLVED (B19)."""
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
        case = _open_case_for_locked(session)
        if case:
            case["status"] = "resolved"
            case["resolved_ts"] = now
            case["resolved_by"] = session
        _save_locked()
    return {"ok": True, "sos": False, "pub_id": pub_id(session)}


def rescue_answer(session: str, case_id: str, accept: bool,
                  reason: str | None = None, now: float | None = None) -> dict[str, Any]:
    """Rescuer ka jawab — 'madad karunga' ya 'nahi paaunga' (+ wajah)."""
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        case = _cases.get(str(case_id))
        if not case or case.get("status") not in ("open", "assigned"):
            return {"ok": False, "error": "case band/expire ho chuka — rescue pehle hi complete hua ya victim theek hai"}
        off = (case.get("offers") or {}).get(session)
        if not off:
            return {"ok": False, "error": "tumhare paas is case ki request nahi aayi — ho sakta hai tier se bahar ho"}
        if off.get("state") in ("declined", "expired"):
            return {"ok": False, "error": f"tumne pehle {off['state']} kar diya tha — decision final hai"}
        off["state"] = "accepted" if accept else "declined"
        off["answered_ts"] = now
        if not accept and reason:
            off["reason"] = str(reason).strip()[:80] or None
        if accept:
            case["status"] = "assigned"
            payload = _rescue_payload_locked(session, now)
        else:
            payload = None
        _save_locked()
    out: dict[str, Any] = {"ok": True, "state": off["state"], "case_id": case["case_id"]}
    if payload:
        out["rescue"] = payload
    return out


def rescue_complete(session: str, case_id: str, now: float | None = None) -> dict[str, Any]:
    """Rescuer: 'pahunch gaya / sab safe' → case RESOLVE + victim ka SOS
    auto-clear (victim ke agle ping mein sos_resolved ki khabar)."""
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        case = _cases.get(str(case_id))
        if not case or case.get("status") not in ("open", "assigned"):
            return {"ok": False, "error": "case pehle hi band ho chuka"}
        off = (case.get("offers") or {}).get(session)
        if not off or off.get("state") != "accepted":
            return {"ok": False, "error": "sirf accepted rescuer hi rescue complete mark kar sakta hai"}
        case["status"] = "resolved"
        case["resolved_ts"] = now
        case["resolved_by"] = session
        victim = _boats.get(case["victim"])
        victim_pid = pub_id(case["victim"])
        if victim:
            victim["sos"] = False
            victim.pop("sos_ts", None)
            victim.pop("sos_note", None)
        _save_locked()
    return {"ok": True, "resolved": True, "case_id": case["case_id"],
            "victim_pub_id": victim_pid}


def stop(session: str, now: float | None = None) -> dict[str, Any]:
    """Beacon OFF = POORA delete. Privacy promise: OFF ka matlab OFF."""
    now = time.time() if now is None else now
    with _lock:
        _load_locked()
        _prune_locked(now)
        existed = session in _boats
        b = _boats.pop(session, None)
        if b and b.get("sos"):
            c = _open_case_for_locked(session)
            if c:
                c["status"] = "resolved"
                c["resolved_ts"] = now
                c["resolved_by"] = "victim_stopped"
        for c in _cases.values():
            off = (c.get("offers") or {}).get(session)
            if off and off.get("state") in ("pending", "seen", "accepted"):
                off["state"] = "expired"
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
    """Share-link lookup — family/rescue team sirf pub_id jaanti hai."""
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
        open_cases = [c for c in _cases.values() if c.get("status") in ("open", "assigned")]
    return {
        "active_boats": len(_boats),
        "sos_active": sum(1 for b in _boats.values() if b.get("sos")),
        "open_rescue_cases": len(open_cases),
        "rescues_enroute": sum(1 for c in open_cases
                               if any(o.get("state") == "accepted" for o in (c.get("offers") or {}).values())),
        "oldest_ping_age_sec": int(max(ages)) if ages else 0,
        "auto_delete_after_sec": PING_MAX_AGE_SEC,
        "sos_max_age_sec": SOS_MAX_AGE_SEC,
        "default_radius_nm": DEFAULT_RADIUS_NM,
        "dispatch_tiers_nm": list(DISPATCH_TIERS_NM),
        "escalate_after_sec": ESCALATE_AFTER_SEC,
        "workflow": ("SOS 1-tap → backend khud nearest boats trace karta hai → unke ping "
                     "mein rescue request (accept/decline) → accepted rescuer ka live "
                     "doori/bearing/ETA victim tak — koi link copy nahi, koi manual step nahi"),
        "privacy": ("no login/identity · raw session id never leaves the server · "
                    "positions stored ONLY while the fisher keeps the beacon on · "
                    "auto-delete after 2 h of silence · /live/stop deletes instantly"),
        "model": "AIS-style broadcast + MRCC-style rescue dispatch, fisherfolk phones ke liye",
    }
