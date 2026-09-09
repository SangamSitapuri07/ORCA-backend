# Chlorophyll fix — what changed and why

## TL;DR

You (correctly) said another AI told you the chlorophyll value
(0.93 mg/m³) was wrong. **It was wrong**, but the reason is more
interesting than a bad API call.

## Investigation

For Chennai (13.5, 80.5) on 2026-08-15, in a 0.2° box:

| Source | Box range | Box mean | Nearest cell to (13.5, 80.5) |
|--------|-----------|----------|------------------------------|
| NOAA VIIRS DINEOF (what ORCA used) | **0.22 to 5.14** | 0.93 ❌ | 0.28 |
| ESA OC-CCI v6.0 (IPCC standard) | 0.16 to 0.85 | 0.50 | 0.49 ✓ |
| NASA Aqua MODIS (standard) | similar to OC-CCI | — | — |

The **16× to 23× spread** inside a 0.2° box is real. It's because
Chennai's coast has heavy chlorophyll (coastal bloom, river runoff)
while the open ocean 50 km offshore is oligotrophic (clear blue water).
A 0.2° box (≈ 20 km) straddles that boundary.

ORCA was reporting the **box mean (0.93)**, which doesn't represent
ANY actual point on the map. It's a mathematical average of two
physically incompatible water masses.

## Fix (commit 554beb7)

1. **`pipeline/erddap_chl.py`** — pick the cell **nearest** to the
   click point, not the box mean. Report `box_min`, `box_max`,
   `box_mean` so the user can see the spatial variance.

2. **`pipeline/occci_chl.py`** (NEW) — added **ESA OC-CCI v6.0** as
   an INDEPENDENT cross-check source. IPCC standard, 1 km, no auth.

3. **`pipeline/orca_data.py`** — now fetches OC-CCI in parallel,
   stores `chlorophyll_occci` on the snapshot.

4. **`pipeline/agents/satellite.py`** — compares NOAA vs OC-CCI.
   - If they agree within 3×: `cross_check_ok` (good)
   - If they disagree by >3×: `cross_check_disagree` (warn) — this
     means coastal blooms or sensor issues, surface honestly

5. **`web/components/MapView.tsx`** — **right-click anywhere on the
   map** to analyze a custom point, not just the 8 hardcoded markers.
   You (rightly) asked why only 8 places worked.

6. **`tools/verify_chl_sources.py`** — updated to show nearest cell vs
   box mean, with correct ERDDAP axis order for each dataset.

## Expected new behavior

After this fix, the Chennai offshore analysis should show:
- chlorophyll: **0.31 mg/m³** (nearest cell, was 0.93)
- chlorophyll_occci: **0.49 mg/m³**
- cross_check: ✓ "agrees within 3×"
- satellite agent: "low productivity" (was "productive zone")

The PFZ score will drop (0.31 is below the 0.5-1.5 "productive"
band), so the verdict may change to "neutral" or "not_recommended"
instead of "highly_recommended". **This is correct** — the old
"highly_recommended" verdict was based on a misleading average.

## What I did NOT do (and why)

- **Did not** add a "fake" Indian chlorophyll source. INCOIS's
  chlorophyll OPeNDAP is genuinely broken (see CHL_FIX_NOTES). I
  rewrote `pipeline/incois.py` to admit this honestly.
- **Did not** fall back to ESA OC-CCI as the primary. NOAA is the
  primary (most recent, 9 km DINEOF gap-filled); OC-CCI is the
  cross-check.
- **Did not** keep the old box-mean behavior as an option. It's
  misleading by design — averaging across a coast/offshore boundary
  is a category error.

## To verify on your machine

```powershell
cd $HOME\Desktop\orca-setup\SIH
git pull
git log --oneline -5   # should show 554beb7 "fix(chl)..."
python tools/verify_chl_sources.py
```

Then restart the backend (Ctrl+C, then re-run uvicorn) and click
Chennai on the dashboard. The chlorophyll should now be ~0.31
mg/m³ instead of 0.93.
