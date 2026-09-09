"""ORCA rule-based chat brain — NO LLM, every word traceable to real data.

Deliberately not an LLM (yet — Ollama arrives in a later phase). The
honest version of a chat assistant without an LLM is:

  1. ROUTE  — keyword intent → which agents/tools to run
  2. RUN    — the actual agents + data tools (this is the live "trace")
  3. COMPOSE — sentences assembled from the numbers those runs returned

Every claim in a reply cites the source and can be verified in the
UI's data panel. When data is missing, the reply says so plainly.
"""
from __future__ import annotations

import re
from datetime import date as date_cls
from typing import Any, Generator

from pipeline import alerts as alerts_mod
from pipeline import forecast as fc
from pipeline import incois_pfz, jtwc
from pipeline.advisory import build_advisory
from pipeline.agents import ALL_AGENTS
from pipeline.orca_data import zone_snapshot_cached
from pipeline.reasoner import reason

AGENT_META: dict[str, dict[str, str]] = {
    "ocean":          {"emoji": "🌊", "name": "Ocean Analysis"},
    "satellite":      {"emoji": "🛰️", "name": "Satellite Analysis"},
    "weather":        {"emoji": "🌦️", "name": "Weather & Hazard"},
    "gis":            {"emoji": "🗺️", "name": "GIS & Spatial"},
    "fisheries":      {"emoji": "🎣", "name": "Fisheries / PFZ"},
    "marine_ecology": {"emoji": "🐟", "name": "Marine Ecology"},
    "marine_risk":    {"emoji": "🚨", "name": "Marine Risk"},
    "anomaly":        {"emoji": "🔍", "name": "Anomaly Detection"},
    "validation":     {"emoji": "✅", "name": "Data Validation"},
}

EXTRA_META: dict[str, dict[str, str]] = {
    "incois_pfz": {"emoji": "📍", "name": "INCOIS PFZ advisory lookup"},
    "jtwc":       {"emoji": "🌀", "name": "JTWC cyclone check"},
    "forecast":   {"emoji": "⏱️", "name": "72 h point forecast"},
    "alerts":     {"emoji": "🔔", "name": "Alert engine"},
}

# ── Intent routing ─────────────────────────────────────────────────

_PAT_PFZ = re.compile(
    r"fish|pfz|mach?li|मछली|मच्छी|kaha?n|kaha+an|pakad|catch|tuna|surmai|जाऊं|कहा[nं]",
    re.I)
_PAT_SAFETY = re.compile(
    r"safe|go out|ja[aiey]|nikal|sakte|सकते|जा सकते|jaana|boat|sail|ventur", re.I)
_PAT_HAZARD = re.compile(
    r"cyclone|storm|toofan|tufan|typhoon|hazard|danger|khatra|खतरा|चक्रवात|warning|alert", re.I)
_PAT_DATA = re.compile(
    r"data|source|quality|fresh|sattelite|satellite|कहाँ से|kaise|kyu[n]?\b|why\b", re.I)


def route(message: str) -> dict[str, Any]:
    """Decide which agents + extra tools this question needs."""
    intents: set[str] = set()
    if _PAT_PFZ.search(message):
        intents.add("pfz")
    if _PAT_SAFETY.search(message):
        intents.add("safety")
    if _PAT_HAZARD.search(message):
        intents.add("hazard")
    if _PAT_DATA.search(message):
        intents.add("data_quality")
    if not intents:
        intents.add("safety")  # the most common real question: "can I go?"

    agents: list[str] = []
    extras: list[str] = ["forecast"]  # safe-window & sea state always useful
    if "pfz" in intents:
        agents += ["satellite", "ocean", "fisheries", "marine_ecology"]
        extras += ["incois_pfz"]
    if "safety" in intents:
        agents += ["ocean", "weather", "marine_risk"]
        extras += ["jtwc", "alerts"]
    if "hazard" in intents:
        agents += ["weather", "marine_risk"]
        extras += ["jtwc", "alerts"]
    if "data_quality" in intents:
        agents += ["validation", "anomaly", "satellite"]

    # order agents in the canonical pipeline order, dedup
    order = [name for name, _fn in ALL_AGENTS]
    agents = [a for a in order if a in set(agents)]
    extras = list(dict.fromkeys(extras))
    return {"intents": sorted(intents), "agents": agents, "tools": extras}


# ── Trace runner ───────────────────────────────────────────────────

def run_trace(
    message: str,
    lat: float,
    lon: float,
    target_date: str | None = None,
    include_gfw: bool = False,
) -> dict[str, Any]:
    """Actually run everything. Returns steps + all raw results.

    Steps mirror what judges want to see: which agent ran, which tool,
    and the one-line result — with the real data behind it.
    """
    target_date = target_date or date_cls.today().isoformat()
    routing = route(message)
    steps: list[dict[str, Any]] = []

    # 1. Shared snapshot (10-min cached — the advisory built moments
    # ago for the same point reuses the exact same data)
    snap = zone_snapshot_cached(lat, lon, target_date, include_gfw=include_gfw)
    n_used = len(snap.get("data_sources_used", []))
    steps.append({
        "agent": "data_layer",
        "tool": "zone_snapshot",
        "args": {"lat": lat, "lon": lon, "date": target_date},
        "summary": f"Snapshot built — {n_used} live sources answered.",
    })

    # 2. Agents
    agent_results = []
    for name, fn in ALL_AGENTS:
        if name not in routing["agents"]:
            continue
        args = {"snap": "ZoneSnapshot"}
        if name in ("marine_ecology", "marine_risk"):
            res = fn(snap, agent_results=agent_results)
            args["agent_results"] = f"{len(agent_results)} prior results"
        else:
            res = fn(snap)
        agent_results.append(res)
        n_f = len(res.get("findings", []))
        meta = AGENT_META.get(name, {"emoji": "🤖", "name": name})
        steps.append({
            "agent": name,
            "tool": "analyze",
            "args": args,
            "summary": f"{meta['emoji']} {meta['name']} ✓ {n_f} finding{'s' if n_f != 1 else ''} · risk {res.get('risk_level', '?')}",
            "result": {"summary": res.get("summary"), "risk_level": res.get("risk_level"), "verdict": res.get("verdict")},
        })

    # 3. Extra tools
    extra_results: dict[str, Any] = {}
    for tool in routing["tools"]:
        try:
            if tool == "incois_pfz":
                r = incois_pfz.nearest_pfz(lat, lon)
                extra_results[tool] = r
                if r.get("found"):
                    s = f"📍 Official PFZ: {r['distance_nm']} NM away ({r.get('sector_name')}, {r.get('advisory_date')})"
                else:
                    s = f"📍 {r.get('note', 'No official PFZ line nearby.')}"
            elif tool == "jtwc":
                r = jtwc.nearest_cyclone(lat, lon)
                extra_results[tool] = r
                if r.get("found"):
                    c = r["cyclone"]
                    s = f"🌀 '{c.get('name') or c['designation']}' at {r['distance_km']} km ({c.get('intensity')})"
                else:
                    s = f"🌀 {r.get('note', 'No active cyclone.')}"
            elif tool == "forecast":
                r = fc.get_point_forecast(lat, lon)
                extra_results[tool] = r
                n48 = r.get("next48h", {})
                s = (f"⏱️ Next 48 h: waves ≤ {n48.get('wave_max_m')} m, "
                     f"wind ≤ {n48.get('wind_max_kn')} kn")
            elif tool == "alerts":
                r = alerts_mod.evaluate(lat, lon)
                extra_results[tool] = r
                s = (f"🔔 {len(r)} active alert(s) for this point."
                     if r else "🔔 All clear — no threshold crossed.")
            else:
                continue
            meta = EXTRA_META.get(tool, {"emoji": "🛠️", "name": tool})
            # extra-tool summaries already start with their emoji — don't duplicate it
            steps.append({"agent": tool, "tool": tool, "args": {"lat": lat, "lon": lon},
                          "summary": f"{meta['name']} ✓ {s}"})
        except Exception as e:  # noqa: BLE001
            steps.append({"agent": tool, "tool": tool, "args": {},
                          "summary": f"⚠️ {tool} failed: {type(e).__name__} — continuing without it."})
            extra_results[tool] = {"error": f"{type(e).__name__}: {e}"}

    # 4. Advisory (single source of truth for the verdict)
    advisory = build_advisory(lat, lon, target_date, include_gfw=include_gfw)

    # 5. Final insight (reuse the proven reasoner for baseline wording)
    insight = reason(snap, include_agents=routing["agents"]) if routing["agents"] else None

    return {
        "routing": routing,
        "steps": steps,
        "snapshot": snap,
        "agent_results": agent_results,
        "extra": extra_results,
        "advisory": advisory,
        "insight": insight,
    }


# ── Answer composition ─────────────────────────────────────────────

def compose_answer(trace: dict[str, Any], message: str) -> str:
    """Assemble reply text from real results. Facts only, source-tagged."""
    routing = trace["routing"]
    adv = trace["advisory"]
    v = adv["variables"]
    parts: list[str] = []

    # Verdict first — the fisher wants the answer in 5 seconds
    parts.append(f"{adv['icon']} {adv['headline_en']}")

    if "pfz" in routing["intents"]:
        fish = next((a for a in trace["agent_results"] if a["agent"] == "fisheries"), None)
        if fish and fish.get("verdict") not in (None, "unknown"):
            parts.append(f"🎣 Fishing verdict: {fish['verdict'].replace('_', ' ')}.")
        if v.get("nearest_pfz_nm") is not None:
            parts.append(
                f"Nearest official INCOIS PFZ is {v['nearest_pfz_nm']} NM "
                f"{v.get('nearest_pfz_bearing') or ''} from you "
                f"(advisory of {v.get('pfz_advisory_date')}).")
        chl = v.get("chlorophyll_mg_m3")
        if chl is not None:
            parts.append(f"Chlorophyll here: {chl:.2f} mg/m³ "
                         + ("(productive water ✓)." if 0.5 <= chl <= 5 else "(not strong feeding water)."))
        fr = trace["extra"].get("forecast", {})
        sw = fc.find_safe_window(fr) if fr else {"found": False}
        if sw.get("found"):
            parts.append(f"Safe sailing window: {sw['from_utc'][:16].replace('T',' ')} → "
                         f"{sw['to_utc'][11:16]} UTC ({sw['hours']} h).")

    if "safety" in routing["intents"] or "hazard" in routing["intents"]:
        for r in adv["reasons"]:
            if r["severity"] in ("no_go", "caution"):
                parts.append(r["msg"])
        if not any(r["severity"] in ("no_go", "caution") for r in adv["reasons"]):
            bits = []
            if v.get("wave_height_m") is not None:
                bits.append(f"waves {v['wave_height_m']} m")
            if v.get("wind_kts") is not None:
                bits.append(f"wind {v['wind_kts']:.0f} kn")
            if v.get("sst_c") is not None:
                bits.append(f"SST {v['sst_c']}°C")
            if bits:
                parts.append("Now: " + ", ".join(bits) + ".")
        parts.append(v.get("cyclone_note", ""))

    if "data_quality" in routing["intents"]:
        used = adv.get("sources", [])
        failed = adv.get("sources_failed", [])
        parts.append(f"Data: {len(used)} sources live ({'; '.join(used[:4])}).")
        if failed:
            parts.append(f"Issues: {failed[0]}" + (f" (+{len(failed)-1} more)" if len(failed) > 1 else ""))

    sw = adv.get("safe_window", {})
    if sw.get("found") and "pfz" not in routing["intents"]:
        parts.append(f"⏱️ Safe window: {sw['from_utc'][:16].replace('T', ' ')} → {sw['to_utc'][11:16]} UTC.")

    if trace.get("insight") and trace["insight"].get("recommendation"):
        parts.append(trace["insight"]["recommendation"])

    parts.append(f"Sources: {len(adv.get('sources', []))} live · advisory valid till "
                 f"{adv['valid_until'][11:16]} UTC. {adv['disclaimer']}")
    return "\n".join(p for p in parts if p)


# ── Event generators (WS + HTTP share the same core) ───────────────

def stream_events(
    message: str,
    lat: float,
    lon: float,
    target_date: str | None = None,
    include_gfw: bool = False,
    lang: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Yield blueprint-shaped chat events with REAL data behind each:
        chat.routing → chat.agent_step (×N) → chat.token (×N) → chat.final
    """
    yield {"type": "chat.routing", "payload": {
        "agents": route(message)["agents"], "tools": route(message)["tools"],
    }}

    trace = run_trace(message, lat, lon, target_date, include_gfw=include_gfw)

    for st in trace["steps"]:
        yield {"type": "chat.agent_step", "payload": st}

    answer = compose_answer(trace, message)
    words = answer.split(" ")
    buf: list[str] = []
    for i, w in enumerate(words):
        buf.append(w)
        if len(buf) == 3 or i == len(words) - 1:
            yield {"type": "chat.token", "payload": {"delta": " ".join(buf) + (" " if i < len(words) - 1 else "")}}
            buf = []

    layers = ["official_pfz"] if "pfz" in trace["routing"]["tools"] else []
    if trace["extra"].get("jtwc", {}).get("found"):
        layers += ["cyclone"]
    yield {"type": "chat.final", "payload": {
        "answer": answer,
        "advisory": trace["advisory"],
        "layers": layers,
        "routing": trace["routing"],
        "sources": trace["advisory"].get("sources", []),
        "lang": lang or "en",
    }}


def answer_once(
    message: str,
    lat: float,
    lon: float,
    target_date: str | None = None,
    include_gfw: bool = False,
    lang: str | None = None,
) -> dict[str, Any]:
    """One-shot (non-streaming) answer — WebSocket fallback path."""
    final: dict[str, Any] | None = None
    steps: list[dict[str, Any]] = []
    for ev in stream_events(message, lat, lon, target_date, include_gfw, lang):
        if ev["type"] == "chat.agent_step":
            steps.append(ev["payload"])
        elif ev["type"] == "chat.final":
            final = ev["payload"]
    assert final is not None
    final["steps"] = steps
    return final
