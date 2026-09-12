"""Agent 1: Ocean Analysis 🌊

Reports SST and wave context from Open-Meteo Marine API data. It applies the
ORCA Phase-1 wave thresholds only to the short-term point forecast; historical
window values and SST remain context and never become fishing/safety proof.

Inputs: ZoneSnapshot (from orca_data)
Outputs: dict of findings:
  {
    "agent": "ocean",
    "findings": [
      {"type": "sst_optimal", "severity": "info", "value": 29.0, "msg": "..."},
      {"type": "wave_warning", "severity": "warn", "value": 3.2, "msg": "..."},
      ...
    ],
    "summary": "SST within optimal range for pelagic fish; waves approaching small-craft caution.",
    "risk_level": "moderate",  # low | moderate | high | critical
  }
"""
from __future__ import annotations

from typing import Any


def analyze(snap: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    sst_max = snap.get("sst_max")
    sst_min = snap.get("sst_min")
    sst_mean = snap.get("sst_mean")
    wave_max = snap.get("wave_max")
    wave_mean = snap.get("wave_mean")

    if sst_mean is not None:
        findings.append({
            "type": "sst_observation",
            "severity": "info",
            "value": sst_mean,
            "unit": "degC",
            "observed_for": snap.get("date"),
            "retrieved_at": snap.get("fetched_at"),
            "source": "Open-Meteo Marine API via ORCA snapshot",
            "msg": f"Mean SST observation {sst_mean}°C; no species, catch, or safety inference was made.",
        })

    # These max/min values span the requested historical window; their
    # difference is temporal range, not evidence of a spatial thermal front.
    if sst_max is not None and sst_min is not None:
        sst_range = sst_max - sst_min
        findings.append({
            "type": "sst_window_range",
            "severity": "info",
            "value": sst_range,
            "unit": "degC",
            "observed_for": snap.get("date"),
            "retrieved_at": snap.get("fetched_at"),
            "source": "Open-Meteo Marine API via ORCA snapshot",
            "msg": f"SST range over the requested window: {sst_range:.1f}°C; this is not a spatial-front diagnosis.",
        })

    # Wave analysis — ORCA Phase-1 configured thresholds (not a
    # vessel-specific or official small-craft certification).
    # wave_now / wave_peak_48h come from the point forecast (attached to
    # the snapshot in orca_data). wave_max here is the PAST ~30-day
    # window maximum — shown as clearly-labelled HISTORY only, never as
    # "today's sea state". (Screenshot review: the panel quoted "Max wave
    # height 2.4 m" while the advisory card read 1.48 m — same place,
    # same time, two unlabeled semantics reading as a contradiction.)
    wave_now = snap.get("wave_now_m")
    wave_peak = snap.get("wave_peak_48h_m")
    if wave_peak is not None:
        now_txt = f"{wave_now} m now, " if wave_now is not None else ""
        h = wave_peak
        if h >= 4.0:
            findings.append({
                "type": "wave_warning_high",
                "severity": "high",
                "value": h,
                "msg": (f"Peak wave height {h} m expected in next 48 h ({now_txt}"
                        "HIGH sea state — small craft should not venture out)."),
            })
        elif h >= 2.5:
            findings.append({
                "type": "wave_caution",
                "severity": "warn",
                "value": h,
                "msg": (f"Peak waves up to {h} m expected in next 48 h ({now_txt}"
                        "rough seas — exercise caution)."),
            })
        else:
            findings.append({
                "type": "wave_calm",
                "severity": "good",
                "value": h,
                "msg": (f"Wave evidence: {now_txt}peak {h} m in next 48 h "
                        "— below ORCA's configured caution threshold."),
            })
        if wave_max is not None:
            findings.append({
                "type": "wave_recent_window",
                "severity": "info",
                "value": wave_max,
                "msg": (f"Past ~30-day window max: {wave_max} m "
                        "(history for context — NOT today's condition)."),
            })
    elif wave_max is not None:
        # Historical context cannot substitute for a short-term forecast.
        findings.append({
            "type": "wave_recent_window",
            "severity": "info",
            "value": wave_max,
            "unit": "m",
            "observed_for": snap.get("date"),
            "retrieved_at": snap.get("fetched_at"),
            "source": "Open-Meteo Marine API via ORCA snapshot",
            "msg": (f"Past-window wave maximum {wave_max} m; the short-term "
                    "forecast is unavailable, so current wave risk is unknown."),
        })

    from pipeline.agents import risk_from_findings
    complete_wave_evidence = wave_now is not None and wave_peak is not None
    risk = risk_from_findings(findings, has_data=complete_wave_evidence)

    if wave_peak is None:
        summary = "Short-term wave evidence unavailable; SST/history are context only."
    elif risk in ("high", "moderate"):
        summary = "Short-term wave forecast crosses an ORCA configured threshold."
    else:
        summary = "Short-term wave forecast is below ORCA's configured wave thresholds."

    for finding in findings:
        if finding.get("type", "").startswith("wave_"):
            finding.setdefault("unit", "m")
            finding.setdefault("observed_for", snap.get("date"))
            finding.setdefault("retrieved_at", snap.get("fetched_at"))
            finding.setdefault("source", "Open-Meteo Marine API via ORCA snapshot/point forecast")

    return {
        "agent": "ocean",
        "findings": findings,
        "summary": summary,
        "risk_level": risk,
        "evidence": {
            "wave_now_available": wave_now is not None,
            "wave_outlook_available": wave_peak is not None,
            "complete": complete_wave_evidence,
        },
    }
