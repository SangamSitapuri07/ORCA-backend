# Safe Departure Window — v2 (aligned to the SIH-2026 threshold spec) for `prabhbani/ORCA-SIH-2026`

> v1 (commit `4d7363a`) was checked against the final spec and **core
> logic matched, but 4 changes were needed**. This v2 implements them
> and is tested — 10/10 synthetic cases pass (§4).

## 1. Status: still pending in that repo — inputs already there

- `backend/routes_v1.py:196` — `"safe_window": None` hardcoded; no
  window algorithm anywhere; `hourly_chart` ignores gusts and slices 24 h.
- `snap["hourly_forecast"]` already carries 72 h of `time`,
  `wave_height_m`, `wind_speed_kn`, `wind_gust_kn` (UTC, knots).
  Zero new API calls needed.

## 2. v1 → v2: what matched, what changed

**Already matched in v1 (unchanged):**
- contiguous-run scanning, ≥ 3 h minimum window
- earliest window preference → covers both "currently safe → how long
  it lasts" and "currently unsafe → next window start time"
- peak wave/wind metrics, honest not-found, fail-safe on missing values,
  misaligned marine/wind series trimming, no network calls, one-line wiring

**Changed for v2 (the 4 deltas):**

| # | Spec requirement | v1 had | v2 does |
|---|---|---|---|
| 1 | Three tiers — GOOD 2.0 m / 15 kn / 25 kn, CAUTION 2.5 m / 20 kn / 34 kn, NO-GO at/above | single safe set (2.5 / 20 / 34) | every hour classified GOOD/CAUTION/NO-GO; window quality GOOD only if **all** hours GOOD; `status: AVAILABLE` vs `CAUTION` |
| 2 | Trilingual EN / HI / **TE** | EN + HI only | `recommendation_te` added (that backend is already trilingual — `headline_te` exists) |
| 3 | Output shape `status/start_time/end_time/duration_hours/max_wave_m/max_wind_kn/recommendation_en|hi|te`, timestamps like `2026-09-13T06:00:00Z` | `found/from_utc/to_utc/hours/evidence.*` | exact spec field names; `end_time = start + duration` (exclusive, matches the 06:00→16:00 = 10 h example); extra fields (`max_gust_kn`, `window_quality`, `currently_safe`, `thresholds`, `note`) are clearly additive — drop if unwanted |
| 4 | Evaluate the 24–48 h series; tests live in `test_routes_and_forecast.py` | scanned 72 h; separate test file | default horizon 48 h (parameterized; provider already supplies 72 h); test cases below drop straight into `test_routes_and_forecast.py` |

## 3. Drop-in `backend/safe_window.py` (v2, tested)

```python
"""Safe Departure Window Calculator v2 — ORCA safety-threshold spec.

Three-tier hour classification:
  GOOD     wave < 2.0 m, sustained wind < 15 kn, gust < 25 kn
  CAUTION  wave < 2.5 m, sustained wind < 20 kn, gust < 34 kn
  NO-GO    any value at/above the CAUTION limits (or missing — fail-safe)
A departure window = contiguous non-NO-GO hours (>= MIN_HOURS, default 3);
quality GOOD only if EVERY hour is GOOD. Pure function — no network calls.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

GOOD = {"wave_m": 2.0, "wind_kn": 15.0, "gust_kn": 25.0}
CAUTION = {"wave_m": 2.5, "wind_kn": 20.0, "gust_kn": 34.0}
MIN_HOURS = 3
HORIZON_HOURS = 48          # spec: evaluate the 24-48 h series
IST_OFFSET = timedelta(hours=5, minutes=30)


def _classify(w, wd, g) -> str:
    if w is None or wd is None or g is None:
        return "NO-GO"      # cannot certify safety without evidence
    if w < GOOD["wave_m"] and wd < GOOD["wind_kn"] and g < GOOD["gust_kn"]:
        return "GOOD"
    if w < CAUTION["wave_m"] and wd < CAUTION["wind_kn"] and g < CAUTION["gust_kn"]:
        return "CAUTION"
    return "NO-GO"


def _iso_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ist12(dt_utc: datetime) -> str:
    return (dt_utc + IST_OFFSET).strftime("%I:%M %p").lstrip("0")


def find_safe_departure_window(hourly: Dict[str, Any],
                               min_hours: int = MIN_HOURS,
                               horizon_hours: int = HORIZON_HOURS) -> Dict[str, Any]:
    times: List[str] = hourly.get("time") or []
    waves: List[Optional[float]] = hourly.get("wave_height_m") or []
    winds: List[Optional[float]] = hourly.get("wind_speed_kn") or []
    gusts: List[Optional[float]] = hourly.get("wind_gust_kn") or []
    # waves come from the marine API, winds from the forecast API — trim to common length
    n = min(len(times), len(waves), len(winds), len(gusts))
    if n == 0:
        return {"status": "UNAVAILABLE",
                "note": "No hourly forecast series available.",
                "recommendation_en": "Departure window unknown — no forecast timeline.",
                "recommendation_hi": "पूर्वानुमान उपलब्ध नहीं है, प्रस्थान समय अज्ञात है।",
                "recommendation_te": "సూచన లేనందున బయలుదేరే సమయం తెలియదు."}

    now_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    start = next((i for i in range(n) if times[i] >= now_key), None)
    if start is None:
        return {"status": "UNAVAILABLE",
                "note": "Forecast series is entirely in the past.",
                "recommendation_en": "Departure window unknown — forecast series expired.",
                "recommendation_hi": "पूर्वानुमान समाप्त हो गया है, प्रस्थान समय अज्ञात है।",
                "recommendation_te": "సూచన గడువు ముగింది, బయలుదేరే సమయం తెలియదు."}
    end = min(n, start + horizon_hours)

    classes = [_classify(waves[k], winds[k], gusts[k]) for k in range(start, end)]
    currently_safe = classes[0] != "NO-GO"

    runs, run_start = [], None
    for idx, c in enumerate(classes + ["NO-GO"]):     # sentinel closes a trailing run
        if c != "NO-GO":
            if run_start is None:
                run_start = idx
        elif run_start is not None:
            runs.append((run_start, idx))
            run_start = None
    runs = [(a, b) for (a, b) in runs if (b - a) >= min_hours]

    if not runs:
        return {"status": "UNAVAILABLE",
                "note": f"No {min_hours}h+ departure window within safety limits "
                        f"in the next {horizon_hours}h.",
                "currently_safe": currently_safe,
                "recommendation_en": f"No safe departure window in the next {horizon_hours} hours — sea conditions exceed safety limits.",
                "recommendation_hi": f"अगले {horizon_hours} घंटों में प्रस्थान के लिए कोई सुरक्षित समय नहीं है।",
                "recommendation_te": f"తరువాతి {horizon_hours} గంటల్లో బయలుదేరడానికి సురక్షిత సమయం లేదు.",
                "thresholds": {"good": GOOD, "caution": CAUTION, "min_hours": min_hours}}

    a, b = runs[0]                # earliest qualifying window (covers both cases:
                                  # currently safe -> starts now; unsafe -> next window)
    quality = "GOOD" if all(classes[i] == "GOOD" for i in range(a, b)) else "CAUTION"

    max_wave = max(waves[start + a: start + b])
    max_wind = max(winds[start + a: start + b])
    max_gust = max(gusts[start + a: start + b])

    start_dt = datetime.fromisoformat(times[start + a]).replace(tzinfo=timezone.utc)
    duration = b - a
    end_dt = start_dt + timedelta(hours=duration)     # exclusive end

    s_local, e_local = _ist12(start_dt), _ist12(end_dt)
    if quality == "GOOD":
        recommendation_en = (f"Optimal departure window between {s_local} and {e_local} "
                             f"(max wave {max_wave:.1f} m, max wind {max_wind:.0f} kn).")
        recommendation_hi = f"{s_local} से {e_local} के बीच प्रस्थान के लिए सर्वोत्तम समय।"
        recommendation_te = f"{s_local} నుండి {e_local} వరకు బయలుదేరడానికి అనుకూలమైన సమయం."
    else:
        recommendation_en = (f"Marginal departure window between {s_local} and {e_local} "
                             f"(max wave {max_wave:.1f} m, max wind {max_wind:.0f} kn) — "
                             f"conditions within caution limits; small craft exercise care.")
        recommendation_hi = f"{s_local} से {e_local} तक सीमांत समय है — छोटी नावों को सावधानी बरतनी चाहिए।"
        recommendation_te = f"{s_local} నుండి {e_local} వరకు జాగ్రత్తతో బయలుదేరండి — చిన్న పడవలు జాగ్రత్త వహించాలి."

    return {
        "status": "AVAILABLE" if quality == "GOOD" else "CAUTION",
        "start_time": _iso_z(start_dt),
        "end_time": _iso_z(end_dt),
        "duration_hours": duration,
        "max_wave_m": round(max_wave, 2),
        "max_wind_kn": round(max_wind, 1),
        "max_gust_kn": round(max_gust, 1),            # extra beyond spec — drop if unwanted
        "window_quality": quality,                    # extra beyond spec
        "currently_safe": currently_safe,             # extra beyond spec
        "recommendation_en": recommendation_en,
        "recommendation_hi": recommendation_hi,
        "recommendation_te": recommendation_te,
        "thresholds": {"good": GOOD, "caution": CAUTION, "min_hours": min_hours},
    }
```

Wiring is unchanged — in `routes_v1.py`:

```python
from safe_window import find_safe_departure_window
# replace  "safe_window": None,  with:
        "safe_window": find_safe_departure_window(snap.get("hourly_forecast", {})),
```

## 4. Tests (drop into `backend/test_routes_and_forecast.py`) — 10/10 pass

| # | Case (spec's four named cases in bold) | Expected |
|---|---|---|
| T1 | **safe window, then deteriorating** (gust spike at h9) | AVAILABLE, 9 h, `end_time = start + 9h`, `currently_safe: true` |
| T2 | **delayed safe window** (unsafe 12 h, then safe 36 h) | AVAILABLE, starts at h12, `currently_safe: false` |
| T3 | **24-hour storm** then calm | AVAILABLE, 24 h window after the storm, `max_wave_m` from inside the window |
| T4 | **storm the whole horizon** | UNAVAILABLE + note + trilingual recommendation |
| T5 | gust 28 kn (above GOOD 25, below NO-GO 34) | `status: CAUTION`, `window_quality: CAUTION` |
| T6 | metrics + strings | `max_wave_m`/`max_wind_kn` exact, all three recommendations non-empty |
| T7 | gust series all `None` | UNAVAILABLE (fail-safe — never fabricate) |
| T8 | empty series | UNAVAILABLE + note |
| T9 | safe runs of 2 h everywhere | UNAVAILABLE (below 3 h minimum) |
| T10 | exactly 3 safe hours | AVAILABLE, `duration_hours: 3` |

## 5. Two decisions the spec leaves open (flagging, not deciding)

1. **Status vocabulary**: the example only shows `"AVAILABLE"`. v2 uses
   `AVAILABLE / CAUTION / UNAVAILABLE`, mirroring the GOOD/CAUTION/NO-GO
   verdict tiers the app already uses. If the frontend wants strictly
   two statuses, fold CAUTION into AVAILABLE and keep
   `window_quality` as the differentiator — one-line change.
2. **May CAUTION hours be part of a window?** v2: yes (window usable,
   labelled marginal) — NO-GO hours never are. If only GOOD hours
   should count, change the run condition from `c != "NO-GO"` to
   `c == "GOOD"` — one-line change.

## 6. v2.1 review of the implemented feature (13 Sep 2026)

The teammate's port is **faithful** — the reported live payload matches
v2 field-for-field, and their T1–T10 are exactly this doc's test table.
Three findings from reviewing the reported live output:

### ⚠️ 6.1 The work is NOT on GitHub yet

`prabhbani/ORCA-SIH-2026` `origin/main` is still at `a7af561` — no
`safe_window.py`, no wiring, no tests are pushed. Everything currently
lives only on the author's machine. **Commit and push first**, before
anything else — unreviewable work is one coffee-spill away from being
lost.

### 🐞 6.2 Real bug in the live payload: "between 10:30 AM and 10:30 AM"

The verified 48-hour window produced:

> "Optimal departure window between 10:30 AM and 10:30 AM (max wave
> 1.5 m, max wind 12 kn)."

Start and end display **identically** because `_ist12()` formats only
the time-of-day — a window spanning two midnights (13 Sep → 15 Sep)
loses its dates. A fisherman reads that as nonsense. Two smaller issues
in the same string: a full-horizon window is closed by the *forecast
boundary*, not by weather, and nothing says so; and `12.5 kn` renders
as "12 kn" (Python's round-half-to-even on `:.0f` understates a safety
number).

### ✅ 6.3 The v2.1 patch (tested — 3 new cases + 10 regression, all pass)

Three surgical replacements in `safe_window.py`:

**(a)** Replace `_ist12` with a day-aware, trilingual formatter:

```python
_WEEKDAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "hi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
    "te": ["సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం"],
}

def _ist_local(dt_utc: datetime, lang: str = "en", with_day: bool = False) -> str:
    """IST time-of-day; appends the weekday when the window crosses midnight
    (a 48 h window must NOT read 'between 10:30 AM and 10:30 AM')."""
    local = dt_utc + IST_OFFSET
    t = local.strftime("%I:%M %p").lstrip("0")
    if with_day:
        t += " " + _WEEKDAYS[lang][local.weekday()]
    return t
```

**(b)** In `find_safe_departure_window`, before building the strings:

```python
    crosses_midnight = (start_dt + IST_OFFSET).date() != (end_dt + IST_OFFSET).date()
    s_local = _ist_local(start_dt, "en", crosses_midnight)
    e_local = _ist_local(end_dt,   "en", crosses_midnight)
    s_hi = _ist_local(start_dt, "hi", crosses_midnight)
    e_hi = _ist_local(end_dt,   "hi", crosses_midnight)
    s_te = _ist_local(start_dt, "te", crosses_midnight)
    e_te = _ist_local(end_dt,   "te", crosses_midnight)
    # a window that runs out of forecast (not out of safety) must say so
    horizon_note = ("Window extends to the end of the forecast horizon — "
                    "re-check before it closes." if b == end - start else None)
```

then use `s_hi/e_hi` in `recommendation_hi`, `s_te/e_te` in
`recommendation_te`, add `"note": horizon_note,` to the returned dict,
and change the EN/HI/TE "max wind" display from `{max_wind:.0f}` to
`{max_wind:.1f}` (12.5 kn must not print as "12 kn").

**Result on the exact live case:**

> "Optimal departure window between 10:30 AM **Sun** and 10:30 AM
> **Tue** (max wave 1.5 m, max wind **12.5** kn)."
> `"note": "Window extends to the end of the forecast horizon — re-check
> before it closes."`
> HI: "10:30 AM **रविवार** से 10:30 AM **मंगलवार** के बीच प्रस्थान के लिए
> सर्वोत्तम समय।"
> TE: "10:30 AM **ఆదివారం** నుండి 10:30 AM **మంగళవారం** వరకు
> బయలుదేరడానికి అనుకూలమైన సమయం."

Same-day windows are unchanged (no weekday clutter, `note: null`).

**New tests to add** (alongside T1–T10): T11 fully-safe 48 h series →
weekday appears in all three strings, start ≠ end display, horizon
note present; T12 same-day window → no weekday, no note; T13 wind 12.5
→ "12.5 kn" in the EN string.
