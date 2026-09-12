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
| ESA OC-CCI v6.0 (Climate Change Initiative product) | 0.16 to 0.85 | 0.50 | 0.49 ✓ |
| NASA Aqua MODIS (historical note only; not wired to ORCA) | no retained reproducible response | — | — |

The provider responses showed a **16× to 23× spread** inside the queried
0.2° box. ORCA cannot determine the cause from chlorophyll values alone:
coastal optical-retrieval effects, cloud/quality handling, different products,
dates, and genuine spatial variability are all possible. It must not be called
a bloom, runoff signal, or water-mass boundary without independent evidence.

ORCA was reporting the **box mean (0.93)** rather than the value nearest
the selected coordinate. It blended a spatially heterogeneous patch and was
therefore the wrong quantity for a point probe.

## Fix (commit 554beb7)

1. **`pipeline/erddap_chl.py`** — pick the cell **nearest** to the
   click point, not the box mean. Report `box_min`, `box_max`,
   `box_mean` so the user can see the spatial variance.

2. **`pipeline/occci_chl.py`** (NEW) — added **ESA OC-CCI v6.0** as
   an INDEPENDENT cross-check source. ESA CCI product, 1 km, no auth.

3. **`pipeline/orca_data.py`** — now fetches OC-CCI in parallel,
   stores `chlorophyll_occci` on the snapshot.

4. **`pipeline/agents/satellite.py`** — compares NOAA vs OC-CCI.
   - If they agree within the internal 3× display band: `cross_check_ok`
   - If they disagree by >3×: `cross_check_disagree` (warn)
   - Neither state validates a product or identifies a bloom, cloud, coastal,
     or sensor cause without independent quality evidence.

5. **`web/components/MapView.tsx`** — **right-click anywhere on the
   map** to analyze a custom point, not just the 8 hardcoded markers.
   You (rightly) asked why only 8 places worked.

6. **`tools/verify_chl_sources.py`** — updated to show nearest cell vs
   box mean, with correct ERDDAP axis order for each dataset.

## Recorded regression example (not a current live expectation)

The historical Chennai response used during that fix contained:
- chlorophyll: **0.31 mg/m³** (nearest cell, was 0.93)
- chlorophyll_occci: **0.49 mg/m³**
- cross-source ratio: within the internal 3× display band (not scientific validation)
- satellite agent: sourced chlorophyll context only; no productivity/catch verdict

The old synthetic PFZ score and `highly_recommended`/`not_recommended`
verdicts have since been removed. A generic chlorophyll value is environmental
context, not an official INCOIS PFZ, catch estimate, or fishing recommendation.

## What I did NOT do (and why)

- **Did not** add a "fake" Indian chlorophyll source. The configured INCOIS
  LAS OPeNDAP call failed in this environment; that does not establish that the
  provider is globally broken. `pipeline/incois.py` reports the actual failure.
- **Did not** silently relabel ESA OC-CCI as the primary. NOAA and OC-CCI
  attempts retain separate product identity, dates, values, and failures.
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

Then restart the backend (Ctrl+C, then re-run uvicorn) and click Chennai on
the dashboard. Expect either a nearest-cell value with product/date provenance
or an explicit provider failure—never a fixed historical value or box mean.
