"""B19 Rescue Dispatch tests — MRCC-style workflow, pure/offline.

Flow jo prove hota hai:
  SOS 1-tap → backend KHUD nearest boats trace → unke ping mein request
  (pending → seen) → accept → victim ko live doori/bearing/ETA →
  escalate 10→25→50 NM on no-accept → resolve (victim OR rescuer).
Koi link copy nahi; koi invented data nahi — sab backend se.
"""
from __future__ import annotations

import pytest

from pipeline import live

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCA_LIVE_STORE", str(tmp_path / "live.json"))
    live.reset()
    yield
    live.reset()


V = (13.080, 80.290)   # victim
R1 = (13.100, 80.310)  # rescuer 1 — ~1.7 NM
R2 = (13.120, 80.330)  # rescuer 2 — ~3.4 NM
FAR = (13.350, 80.480) # ~19.6 NM — tier-1 (10) se bahar, tier-2 (25) ke andar


def _three_boats():
    live.start("sess-v", *V, label="SeaStar", now=NOW)
    live.start("sess-r1", *R1, label="RescueOne", now=NOW)
    live.start("sess-r2", *R2, label="RescueTwo", now=NOW)


def test_sos_autodispatches_nearest_boats():
    _three_boats()
    r = live.sos_on("sess-v", note="engine fail", now=NOW)
    assert r["ok"] and r["case"]["status"] == "open"
    assert r["case"]["tier_nm"] == 10.0
    assert r["case"]["dispatched"] == 2       # dono paas ke boats ko request
    assert r["case"]["seen"] == 0             # abhi kisi ne nahi dekha
    assert r["case"]["accepted"] == []


def test_rescuer_gets_request_in_own_ping_and_seen_flips():
    _three_boats()
    live.sos_on("sess-v", now=NOW)
    p = live.ping("sess-r1", *R1, now=NOW + 3)
    req = p["rescue_request"]
    assert req is not None and req["my_state"] == "seen"  # pehle pending tha, ab DEKHA
    assert req["distance_nm"] == pytest.approx(1.68, abs=0.05)
    assert 0 <= req["bearing_deg"] <= 360
    assert req["victim"]["label"] == "SeaStar"
    assert req["expires_in_sec"] > 0
    assert "session" not in str(req)          # privacy: raw session kabhi nahi
    # victim ko pata chala r1 ne dekha
    v = live.ping("sess-v", *V, now=NOW + 4)
    assert v["my_sos"]["seen"] == 1
    assert v["my_sos"]["dispatched"] == 2


def test_non_dispatched_boat_gets_no_request():
    _three_boats()
    # sirf victim + r1 dispatch radius mein — r2 ko bahar nikaal do
    live.stop("sess-r2", now=NOW)
    live.sos_on("sess-v", now=NOW)
    live.start("sess-x", *FAR, now=NOW)       # 25+ NM door
    p = live.ping("sess-x", *FAR, now=NOW + 2)
    assert p["rescue_request"] is None


def test_accept_gives_victim_live_tracking_with_eta():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 3)    # request mili
    a = live.rescue_answer("sess-r1", case["case_id"], accept=True, now=NOW + 5)
    assert a["ok"] and a["state"] == "accepted"
    assert a["rescue"]["my_state"] == "accepted"
    # rescuer ke ping pe guidance aati rahegi (state accepted)
    assert live.ping("sess-r1", *R1, now=NOW + 6)["rescue_request"]["my_state"] == "accepted"
    # victim: 1 aa raha + ETA (r1 speed 6 kn bhej raha hai)
    live.ping("sess-r1", *R1, speed_kn=6.0, now=NOW + 7)
    v = live.ping("sess-v", *V, now=NOW + 8)["my_sos"]
    assert v["status"] == "assigned"
    assert len(v["accepted"]) == 1
    acc = v["accepted"][0]
    assert acc["pub_id"] == live.pub_id("sess-r1") and acc["label"] == "RescueOne"
    assert acc["distance_nm"] == pytest.approx(1.68, abs=0.05)
    assert acc["eta_min"] == pytest.approx(17, abs=2)   # 1.68 NM @ 6 kn ≈ 17 min
    assert acc["age_sec"] == 1


def test_no_speed_no_eta_honest():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 2)
    live.rescue_answer("sess-r1", case["case_id"], True, now=NOW + 3)
    v = live.ping("sess-v", *V, now=NOW + 4)["my_sos"]
    assert v["accepted"][0]["eta_min"] is None  # invent NAHI — speed unknown


def test_decline_with_reason_excludes_and_escalation_works():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    d = live.rescue_answer("sess-r1", case["case_id"], accept=False,
                           reason="khud net mein fasa hoon", now=NOW + 2)
    assert d["ok"] and d["state"] == "declined"
    # declined ko dobara request nahi jaati
    assert live.ping("sess-r1", *R1, now=NOW + 3)["rescue_request"] is None
    v = live.ping("sess-v", *V, now=NOW + 4)["my_sos"]
    assert v["declined"] == 1
    # 60 s kisi ne accept nahi kiya → ESCALATE: tier 10 → 25 NM
    live.start("sess-far", *FAR, label="FarBoat", now=NOW)   # ~24 NM ≈ tier-2 mein aayega
    v2 = live.ping("sess-v", *V, now=NOW + 61)["my_sos"]
    assert v2["tier_nm"] == 25.0
    assert v2["escalate_in_sec"] is not None
    assert live.ping("sess-far", *FAR, now=NOW + 62)["rescue_request"] is not None


def test_accept_stops_escalation():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    live.rescue_answer("sess-r1", case["case_id"], True, now=NOW + 2)
    live.start("sess-far", *FAR, now=NOW)
    assert live.ping("sess-far", *FAR, now=NOW + 200)["rescue_request"] is None


def test_victim_clear_resolves_case_for_everyone():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    live.rescue_answer("sess-r1", case["case_id"], True, now=NOW + 2)
    live.sos_off("sess-v", now=NOW + 10)       # "main theek hoon"
    assert live.ping("sess-r1", *R1, now=NOW + 11)["rescue_request"] is None
    assert live.ping("sess-v", *V, now=NOW + 11)["my_sos"] is None
    # ab answer karna = honest error
    late = live.rescue_answer("sess-r2", case["case_id"], True, now=NOW + 12)
    assert late["ok"] is False


def test_rescuer_complete_autoclears_victim_sos():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    live.rescue_answer("sess-r1", case["case_id"], True, now=NOW + 2)
    done = live.rescue_complete("sess-r1", case["case_id"], now=NOW + 600)
    assert done["ok"] and done["resolved"] is True
    assert done["victim_pub_id"] == live.pub_id("sess-v")
    assert live.sos_list(now=NOW + 600)["count"] == 0        # victim SOS auto-clear
    out = live.ping("sess-v", *V, now=NOW + 601)
    assert out.get("sos_resolved", {}).get("by") == "rescuer"


def test_only_accepted_rescuer_can_complete():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    live.ping("sess-r2", *R2, now=NOW + 1)
    live.rescue_answer("sess-r1", case["case_id"], True, now=NOW + 2)
    bad = live.rescue_complete("sess-r2", case["case_id"], now=NOW + 5)
    assert bad["ok"] is False and "accepted" in bad["error"]


def test_sos_double_press_idempotent_no_duplicate_case():
    _three_boats()
    c1 = live.sos_on("sess-v", now=NOW)["case"]["case_id"]
    c2 = live.sos_on("sess-v", now=NOW + 2)["case"]["case_id"]
    assert c1 == c2                            # panic-me-double-tap = ek hi case


def test_wrong_boat_cannot_answer_case():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.start("sess-x", *FAR, now=NOW)        # request kabhi mili hi nahi
    r = live.rescue_answer("sess-x", case["case_id"], True, now=NOW + 1)
    assert r["ok"] is False


def test_on_rescue_badge_in_nearby():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    live.rescue_answer("sess-r1", case["case_id"], True, now=NOW + 2)
    boats = {b["pub_id"]: b for b in live.nearby(*V, radius_nm=20, now=NOW + 3)["boats"]}
    assert boats[live.pub_id("sess-r1")].get("on_rescue") is True
    assert "on_rescue" not in boats[live.pub_id("sess-r2")]


def test_cases_survive_restart_and_stats():
    _three_boats()
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    live.rescue_answer("sess-r1", case["case_id"], True, now=NOW + 2)
    live._boats.clear(); live._cases.clear(); live._loaded = False
    v = live.ping("sess-v", *V, now=NOW + 3)["my_sos"]
    assert v is not None and v["case_id"] == case["case_id"]
    assert v["status"] == "assigned" and len(v["accepted"]) == 1
    s = live.stats(now=NOW + 3)
    assert s["open_rescue_cases"] == 1 and s["rescues_enroute"] == 1
    assert "link copy nahi" in s["workflow"]
