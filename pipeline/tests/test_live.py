"""B18 Live Beacon ("Samudri Rakshak Net") tests — pure/offline.
Store tmp mein redirect; koi network nahi. Privacy proofs included:
raw session kabhi public response mein nahi, stop = poora delete,
2 h silence = auto-delete, SOS 12 h se zyada nahi."""
from __future__ import annotations

import json

import pytest

from pipeline import live

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCA_LIVE_STORE", str(tmp_path / "live.json"))
    live.reset()
    yield
    live.reset()


# Chennai coast ke aas-paas demo coords
A = (13.08, 80.29)   # boat A
B = (13.10, 80.31)   # boat B — ~1.4 NM door


def test_start_and_nearby_public_shape():
    r = live.start("sess-a-0001", *A, label="Boat A", now=NOW)
    assert r["ok"] and r["created"] and r["pub_id"] != "sess-a-0001"
    res = live.nearby(*A, radius_nm=20, now=NOW)
    assert res["count"] == 1
    b = res["boats"][0]
    assert b["pub_id"] == r["pub_id"]
    assert b["label"] == "Boat A" and b["sos"] is False
    assert b["distance_nm"] == 0.0 and b["age_sec"] == 0
    # PRIVACY PROOF: kisi bhi public dict mein raw session nahi
    assert "session" not in b and "sess-a-0001" not in json.dumps(res)


def test_ping_updates_position_and_autoregisters():
    # phone restart ke baad bina start ke ping — flow kabhi nahi tootta
    r = live.ping("sess-b-0002", *B, now=NOW)
    assert r["ok"] and r["created"] is True and r["sos_nearby_count"] == 0
    live.ping("sess-b-0002", 13.11, 80.32, speed_kn=6.2, heading_deg=145.7, now=NOW + 5)
    res = live.nearby(*A, radius_nm=20, now=NOW + 5)
    b = res["boats"][0]
    assert b["lat"] == 13.11 and b["lon"] == 80.32
    assert b["speed_kn"] == 6.2 and b["heading_deg"] == 146
    assert b["age_sec"] == 0


def test_sos_flow_and_ping_alert_channel():
    live.start("sess-a", *A, now=NOW)
    live.start("sess-b", *B, now=NOW)
    r = live.sos_on("sess-a", note="engine fail, paani aa raha", now=NOW)
    assert r["ok"] and r["sos"] is True and r["sos_age_sec"] == 0
    # B ka NORMAL ping hi alert channel hai — alag polling nahi
    p = live.ping("sess-b", *B, now=NOW + 3)
    assert p["sos_nearby_count"] == 1
    s = p["sos_nearby"][0]
    assert s["sos_note"] == "engine fail, paani aa raha"
    assert 1.0 < s["distance_nm"] < 2.0
    assert 0 <= s["bearing_deg"] <= 360
    # sos list (command center)
    lst = live.sos_list(now=NOW + 3)
    assert lst["count"] == 1
    # theek hoon → clear
    c = live.sos_off("sess-a", now=NOW + 10)
    assert c["ok"] and c["sos"] is False
    assert live.ping("sess-b", *B, now=NOW + 11)["sos_nearby_count"] == 0
    assert live.sos_list(now=NOW + 11)["count"] == 0


def test_sos_unknown_session_still_works_with_coords():
    r = live.sos_on("sess-late", lat=13.09, lon=80.30, now=NOW)
    assert r["ok"] and r["sos"] is True
    assert live.nearby(*A, radius_nm=5, now=NOW)["sos_count"] == 1
    # bina coords ke — honest error (endpoint 404 karega)
    bad = live.sos_on("sess-nope", now=NOW)
    assert bad["ok"] is False and "unknown session" in bad["error"]


def test_distance_bearing_accuracy():
    # ~1 NM seedha NORTH (60.04 NM per 1° latitude)
    d_lat = 1.0 / 60.04
    live.start("sess-n", A[0] + d_lat, A[1], now=NOW)
    res = live.nearby(*A, radius_nm=20, now=NOW)
    d = {b["pub_id"]: b for b in res["boats"]}
    north = d[live.pub_id("sess-n")]
    assert abs(north["distance_nm"] - 1.0) < 0.03
    assert north["bearing_deg"] in (0, 359)  # seedha north


def test_privacy_expiry_auto_delete():
    live.start("sess-old", *A, ts=NOW - (2 * 3600 + 5), now=NOW - (2 * 3600 + 5))
    # 2 h se zyada silent → auto-delete (privacy promise)
    assert live.nearby(*A, radius_nm=100, now=NOW)["count"] == 0
    assert live.by_pub_id(live.pub_id("sess-old"), now=NOW) is None


def test_sos_max_age_12h():
    live.start("sess-sos", *A, now=NOW)
    live.sos_on("sess-sos", now=NOW)
    assert live.sos_list(now=NOW + 3600)["count"] == 1
    # 12 h purana SOS bhi server pe kachda nahi rakhta
    assert live.sos_list(now=NOW + 12 * 3600 + 10)["count"] == 0


def test_stop_deletes_everything_instantly():
    live.start("sess-x", *A, label="Boat X", now=NOW)
    live.sos_on("sess-x", now=NOW)
    pid = live.pub_id("sess-x")
    r = live.stop("sess-x", now=NOW + 1)
    assert r["ok"] and r["deleted"] is True
    assert live.nearby(*A, radius_nm=100, now=NOW + 1)["count"] == 0
    assert live.sos_list(now=NOW + 1)["count"] == 0
    assert live.by_pub_id(pid, now=NOW + 1) is None  # share link bhi dead


def test_radius_filter():
    live.start("sess-far", A[0] + 0.5, A[1], now=NOW)  # ~30 NM north
    assert live.nearby(*A, radius_nm=20, now=NOW)["count"] == 0
    assert live.nearby(*A, radius_nm=40, now=NOW)["count"] == 1


def test_persistence_roundtrip(tmp_path):
    live.start("sess-p", *A, label="Boat P", now=NOW)
    live.sos_on("sess-p", note="help", now=NOW)
    # server restart simulate: memory saaf, file wapas load
    pid = live.pub_id("sess-p")
    live._boats.clear()
    live._loaded = False
    res = live.nearby(*A, radius_nm=20, now=NOW + 2)
    assert res["count"] == 1
    b = res["boats"][0]
    assert b["pub_id"] == pid and b["sos"] is True and b["sos_note"] == "help"


def test_stats_honest():
    live.start("sess-1", *A, now=NOW)
    live.start("sess-2", *B, now=NOW)
    live.sos_on("sess-2", now=NOW)
    s = live.stats(now=NOW + 100)
    assert s["active_boats"] == 2 and s["sos_active"] == 1
    assert s["oldest_ping_age_sec"] == 100
    assert s["auto_delete_after_sec"] == 2 * 3600
    assert "no login" in s["privacy"]
