"""B20 tests — watch/listen mode, late-joiner re-dispatch, ORCA Radio comms.
User report: "request tabhi jaati jab dono ka beacon ON ho; baad mein
start karne pe kuch nahi aata; radio connection bhi ho" — sab yahin prove.
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


V = (13.080, 80.290)
R1 = (13.100, 80.310)
FAR = (13.350, 80.480)   # ~19.6 NM — tier-1 bahar, tier-2 andar


def test_late_joiner_gets_request_without_resos():
    """ROOT BUG FIX: victim ka SOS pehle, rescuer ka beacon BAAD mein —
    fir bhi pehle ping mein hi request mil jaani chahiye."""
    live.start("sess-v", *V, label="SeaStar", now=NOW)
    live.sos_on("sess-v", note="engine fail", now=NOW)
    # rescuer 10 min BAAD online aaya — koi re-SOS nahi
    live.start("sess-r1", *R1, label="RescueOne", now=NOW + 600)
    p = live.ping("sess-r1", *R1, now=NOW + 605)
    assert p["rescue_request"] is not None
    assert p["rescue_request"]["victim"]["label"] == "SeaStar"


def test_watch_mode_receives_alerts_with_coarse_privacy():
    """LISTENER (bina beacon) bhi SOS sun le — par position ~11 km ROUND
    ho ke store ho (exact trail kabhi nahi — privacy)."""
    live.start("sess-v", *V, now=NOW)
    live.sos_on("sess-v", now=NOW)
    p = live.ping("sess-w1", 13.067, 80.244, watch=True, now=NOW + 2)
    assert p["ok"] and p["rescue_request"] is not None    # alert mil gayi
    # server ke paas stored position COARSE hai (0.1° grid)
    b = live._boats["sess-w1"]
    assert b["mode"] == "watch"
    assert abs(b["lat"] - 13.1) < 1e-9 and abs(b["lon"] - 80.2) < 1e-9
    # listener radar pe NAHI dikhta (privacy) — sirf count hota hai
    res = live.nearby(*V, radius_nm=20, now=NOW + 3)
    pubs = [x["pub_id"] for x in res["boats"]]
    assert live.pub_id("sess-w1") not in pubs
    assert res["watchers"] == 1
    s = live.stats(now=NOW + 3)
    assert s["watchers"] == 1 and s["active_boats"] == 1   # sirf victim beacon


def test_sos_from_watch_mode_forces_exact_beacon():
    """Listener khud mushkil mein aa jaaye → uska SOS EXACT ho jaata hai
    (rescue ke liye zaroori; consent = khud dabaya)."""
    live.ping("sess-w2", 13.067, 80.244, watch=True, now=NOW)
    live.sos_on("sess-w2", lat=13.0673, lon=80.2441, note="boat toot gayi", now=NOW + 1)
    b = live._boats["sess-w2"]
    assert b["mode"] == "beacon"
    assert b["lat"] == pytest.approx(13.0673)             # exact — rounded nahi
    assert live.nearby(*V, radius_nm=20, now=NOW + 2)["sos_count"] == 1


def test_watch_accept_flips_to_exact_tracking():
    """Listener MADAD accept kare → rescue tracking ke liye mode beacon."""
    live.start("sess-v", *V, now=NOW)
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-w3", 13.10, 80.29, watch=True, now=NOW + 2)   # request mili
    r = live.rescue_answer("sess-w3", case["case_id"], True, now=NOW + 3)
    assert r["ok"] and r["rescue"]["my_state"] == "accepted"
    assert live._boats["sess-w3"]["mode"] == "beacon"


def test_orca_radio_two_way_and_permissions():
    """Radio: victim ↔ accepted rescuer. Others = honest mana. Feed ping
    responses ke andar hi aata hai."""
    live.start("sess-v", *V, label="SeaStar", now=NOW)
    live.start("sess-r1", *R1, label="RescueOne", now=NOW)
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    cid = case["case_id"]
    live.rescue_answer("sess-r1", cid, True, now=NOW + 2)
    # victim boli
    m1 = live.rescue_msg("sess-v", cid, "paani ghus raha hai, jaldi aao", now=NOW + 5)
    assert m1["ok"] and m1["count"] == 1
    # rescuer ka preset
    m2 = live.rescue_msg("sess-r1", cid, "🌊 leher zyada hai, dheere aana", preset=True, now=NOW + 6)
    assert m2["ok"] and m2["count"] == 2
    # delivery: rescuer ke rescue_request.messages
    req = live.ping("sess-r1", *R1, now=NOW + 7)["rescue_request"]
    msgs = req["messages"]
    assert [m["text"] for m in msgs] == ["paani ghus raha hai, jaldi aao", "🌊 leher zyada hai, dheere aana"]
    assert msgs[0]["mine"] is False and msgs[1]["mine"] is True
    assert msgs[1]["preset"] is True
    # delivery: victim ke my_sos.messages
    mine = live.ping("sess-v", *V, now=NOW + 8)["my_sos"]["messages"]
    assert mine[0]["mine"] is True and mine[1]["mine"] is False
    # stranger nahi bol sakta
    live.start("sess-x", *R1, now=NOW)
    bad = live.rescue_msg("sess-x", cid, "hello", now=NOW + 9)
    assert bad["ok"] is False and "victim" in bad["error"]


def test_radio_dead_after_resolve():
    live.start("sess-v", *V, now=NOW)
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.sos_off("sess-v", now=NOW + 10)
    r = live.rescue_msg("sess-v", case["case_id"], "theek hoon sab", now=NOW + 11)
    assert r["ok"] is False and "band" in r["error"]


def test_msg_cap_30_and_empty_rejected():
    live.start("sess-v", *V, now=NOW)
    cid = live.sos_on("sess-v", now=NOW)["case"]["case_id"]
    assert live.rescue_msg("sess-v", cid, "", now=NOW)["ok"] is False
    for i in range(35):
        live.rescue_msg("sess-v", cid, f"msg {i}", now=NOW + i)
    msgs = live.ping("sess-v", *V, now=NOW + 40)["my_sos"]["messages"]
    assert len(msgs) == 20                                # view limit
    assert len(live._cases[cid]["messages"]) == 30        # stored cap


def test_escalation_timer_not_reset_by_empty_dispatch():
    """Koi boat aas-paas nahi → ping pe re-dispatch khaali → timer waisa hi;
    60s pe tier badhna chahiye, aur tab aayi far boat ko request jaaye."""
    live.start("sess-v", *V, now=NOW)
    live.sos_on("sess-v", now=NOW)
    v1 = live.ping("sess-v", *V, now=NOW + 30)["my_sos"]   # koi dispatch naulne
    assert v1["tier_nm"] == 10.0 and v1["dispatched"] == 0
    live.start("sess-far", *FAR, label="FarBoat", now=NOW + 40)
    v2 = live.ping("sess-v", *V, now=NOW + 61)["my_sos"]
    assert v2["tier_nm"] == 25.0                          # escalate hua
    assert live.ping("sess-far", *FAR, now=NOW + 62)["rescue_request"] is not None


def test_late_joiner_never_spams_declined_boat():
    live.start("sess-v", *V, now=NOW)
    live.start("sess-r1", *R1, now=NOW)
    case = live.sos_on("sess-v", now=NOW)["case"]
    live.ping("sess-r1", *R1, now=NOW + 1)
    live.rescue_answer("sess-r1", case["case_id"], False, now=NOW + 2)
    # jitni baar bhi ping kare — declined ko request NAHI (marzi respect)
    for i in range(3):
        assert live.ping("sess-r1", *R1, now=NOW + 10 + i * 5)["rescue_request"] is None
