# Safe Departure Window — status check + drop-in implementation for `prabhbani/ORCA-SIH-2026`

> Checked 13 Sep 2026 against clone `a7af561`. Question: is the Safe
> Departure Window Calculator for `/api/v1/advisory` still pending, and
> how should it be built?

## 1. Status: YES, pending — and the inputs are already there

**Pending (the gap):**
- `backend/routes_v1.py` line 196: `"safe_window": None` — **hardcoded**,
  never computed. The advisory response always ships a null window.
- No window algorithm exists anywhere in the repo.
  `agents_engine.py` only does a worst-case fold of the **current**
  values for the verdict — nothing looks at the future series.
- The `hourly_chart` slices `[:24]` and ignores the gust series.

**Already working (the inputs):**
- `backend/data_providers.py` fetches **72 h** of hourly series
  (`forecast_days: 3`, UTC) from Open-Meteo and stores them in
  `snap["hourly_forecast"]`:
  - `time` — ISO UTC hourly timestamps (from the forecast API)
  - `wave_height_m` — from the **marine** API hourly `wave_height`
  - `wind_speed_kn` — hourly `wind_speed_10m` (already in knots)
  - `wind_gust_kn` — hourly `wind_gusts_10m` (already in knots)

So this is purely a computation + wiring task: **zero new API calls**,
zero credentials, zero new dependencies.

## 2. Drop-in implementation (tested — 9/9 synthetic cases pass)

### 2a. New file `backend/safe_window.py`

Pure function over the existing `hourly_forecast` dict. Thresholds per
the task spec (waves < 2.5 m, sustained wind < 20 kn, gusts < 34 kn —
34 kn is the gale/small-craft warning onset; ORCA-backend's own
`pipeline/forecast.py::find_safe_window` uses 30 kn — both are
defensible, keep them as constants). Missing values never certify
safety (fail-safe). The code below is exactly what passed the tests in
§3.

```python
"""Safe Departure Window Calculator — pure function over the live
Open-Meteo hourly series (time, wave_height_m, wind_speed_kn, wind_gust_kn).
No network calls; missing values never certify safety (fail-safe)."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

WAVE_MAX_M = 2.5      # small-craft wave caution level (INCOIS bulletin practice)
WIND_MAX_KN = 20.0    # ~Beaufort 5 sustained — workable but tiring
GUST_MAX_KN = 34.0    # gale onset / small-craft warning level
MIN_HOURS = 3         # a usable fishing round needs >= 3 contiguous safe hours
HORIZON_HOURS = 72    # provider fetches forecast_days=3
IST_OFFSET = timedelta(hours=5, minutes=30)


def _fmt_ist(iso_utc: str) -> str:
    try:
        t = datetime.fromisoformat(iso_utc).replace(tzinfo=timezone.utc)
        return (t + IST_OFFSET).strftime("%I:%M %p IST").lstrip("0")
    except ValueError:
        return iso_utc


def _hour_ok(w, wd, g) -> bool:
    if w is None or wd is None or g is None:
        return False          # cannot certify safety without evidence
    return w < WAVE_MAX_M and wd < WIND_MAX_KN and g < GUST_MAX_KN


def find_safe_departure_window(hourly: Dict[str, Any]) -> Dict[str, Any]:
    times: List[str] = hourly.get("time") or []
    waves: List[Optional[float]] = hourly.get("wave_height_m") or []
    winds: List[Optional[float]] = hourly.get("wind_speed_kn") or []
    gusts: List[Optional[float]] = hourly.get("wind_gust_kn") or []
    # wave series comes from the marine API, wind from the forecast API —
    # trim to the common length so indices always line up
    n = min(len(times), len(waves), len(winds), len(gusts))
    thresholds = {"wave_max_m": WAVE_MAX_M, "wind_max_kn": WIND_MAX_KN,
                  "gust_max_kn": GUST_MAX_KN, "min_hours": MIN_HOURS}
    if n == 0:
        return {"found": False, "note": "No hourly forecast series available.",
                "thresholds": thresholds}

    now_key = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    start = 0
    for i in range(n):
        if times[i] >= now_key:
            start = i
            break
    else:
        return {"found": False, "note": "Forecast series is entirely in the past.",
                "thresholds": thresholds}
    end = min(n, start + HORIZON_HOURS)

    runs = []
    run_start = None
    for k in range(start, end):
        if _hour_ok(waves[k], winds[k], gusts[k]):
            if run_start is None:
                run_start = k
        elif run_start is not None:
            runs.append((run_start, k))
            run_start = None
    if run_start is not None:
        runs.append((run_start, end))
    runs = [(a, b) for (a, b) in runs if (b - a) >= MIN_HOURS]

    if not runs:
        return {"found": False,
                "note": f"No {MIN_HOURS}h+ departure window within limits "
                        f"in the next {HORIZON_HOURS}h.",
                "thresholds": thresholds}

    a, b = runs[0]                       # earliest window = what a fisher asks for
    worst_wave = max(waves[a:b])
    worst_wind = max(winds[a:b])
    worst_gust = max(gusts[a:b])

    reason = None
    next_change_utc = None
    if b < end:
        next_change_utc = times[b]
        if waves[b] is not None and waves[b] >= WAVE_MAX_M:
            reason = f"waves build to {waves[b]:.1f} m"
        elif gusts[b] is not None and gusts[b] >= GUST_MAX_KN:
            reason = f"gusts reach {gusts[b]:.0f} kn"
        elif winds[b] is not None and winds[b] >= WIND_MAX_KN:
            reason = f"sustained wind hits {winds[b]:.0f} kn"
        else:
            reason = "a data gap (values unavailable)"
        caution = f"Caution after {_fmt_ist(times[b])} — {reason}."
    else:
        caution = "Window extends to the end of the forecast horizon."

    return {
        "found": True,
        "from_utc": times[a] + "Z",
        "to_utc": times[b - 1] + "Z",
        "hours": b - a,
        "headline_en": (f"Safe to depart between {_fmt_ist(times[a])} and "
                        f"{_fmt_ist(times[b - 1])}. {caution}"),
        "headline_hi": (f"{_fmt_ist(times[a])} से {_fmt_ist(times[b - 1])} तक निकलना "
                        f"सुरक्षित है। {caution}"),
        "evidence": {
            "worst_wave_m": worst_wave, "worst_wind_kn": worst_wind,
            "worst_gust_kn": worst_gust, "next_change_utc": next_change_utc,
            "reason_after": reason, "windows_found": len(runs),
        },
        "thresholds": thresholds,
    }
```

### 2b. Wire it in `backend/routes_v1.py` — one line

```python
from safe_window import find_safe_departure_window   # top of file

# in get_advisory(), replace:
        "safe_window": None,
# with:
        "safe_window": find_safe_departure_window(snap.get("hourly_forecast", {})),
```

Keep the existing `safe_window` key (the app already receives it); if
the frontend expects the spec's name, add
`"safe_departure_window": <same object>` as an alias.

### 2c. Example response

```json
"safe_window": {
  "found": true,
  "from_utc": "2026-09-13T05:00Z",
  "to_utc": "2026-09-13T13:00Z",
  "hours": 9,
  "headline_en": "Safe to depart between 10:30 AM IST and 6:30 PM IST. Caution after 7:30 PM IST — gusts reach 36 kn.",
  "headline_hi": "10:30 AM IST से 6:30 PM IST तक निकलना सुरक्षित है। Caution after 7:30 PM IST — gusts reach 36 kn.",
  "evidence": {"worst_wave_m": 1.0, "worst_wind_kn": 10.0, "worst_gust_kn": 18.0,
               "next_change_utc": "2026-09-13T14:00Z", "reason_after": "gusts reach 36 kn",
               "windows_found": 2},
  "thresholds": {"wave_max_m": 2.5, "wind_max_kn": 20.0, "gust_max_kn": 34.0, "min_hours": 3}
}
```

Not-found is honest: `{"found": false, "note": "No 3h+ departure window
within limits in the next 72h.", "thresholds": {...}}` — never a
fabricated window.

## 3. Tests to add (`backend/test_safe_window.py`)

All of these were run against the code above — 9/9 pass:

| # | Case | Expected |
|---|---|---|
| 1 | 9 safe hours then a 36 kn gust spike | found, 9 h, `reason_after: "gusts reach 36 kn"` |
| 2 | gust spike every 3rd hour (max run 2 h) | `found: false` + note |
| 3 | gust series all `None` | `found: false` (fail-safe, no fabrication) |
| 4 | empty series | `found: false` + "No hourly forecast series available." |
| 5 | safe through the whole horizon | found, `next_change_utc: null`, "extends to end of horizon" |
| 6 | wave breach at the boundary | `reason_after: "waves build to 3.0 m"` |
| 7 | headline formatting | bilingual strings contain IST times |
| 8 | marine series shorter than wind series | trimmed to common length, no crash |
| 9 | short early window + longer later window | **earliest** window returned (4 h), `windows_found: 2` |

## 4. Small extras worth doing in the same PR

- `hourly_chart`: include `gust_kn` per hour and use the full 48–72 h
  instead of `[:24]` — the data is already in `hourly_forecast`.
- The provider's `httpx` timeout is 12 s for both Open-Meteo calls —
  fine for these, but see `SIH2026_BACKEND_DIAGNOSIS.md` for the MOSDAC
  timeout problem.
- Reference implementation to diff against: this repo's
  `pipeline/forecast.py::find_safe_window()` + its wiring in
  `pipeline/advisory.py` — in production here since 3 Sep 2026, same
  thresholds except gusts (30 kn there, 34 kn in the task spec).
