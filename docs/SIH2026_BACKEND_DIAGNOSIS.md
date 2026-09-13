# Diagnosis — why the 3 MOSDAC datasets failed in `prabhbani/ORCA-SIH-2026` backend

> Checked 13 Sep 2026 against `github.com/prabhbani/ORCA-SIH-2026` (clone of
> `a7af561`, files `backend/mosdac_datasets.py`, `backend/mosdac_provider.py`,
> `backend/mosdac_parsers.py`, `backend/MOSDAC_INTEGRATION.md`) and against
> the LIVE MOSDAC OpenSearch API (`/apios/datasets.json` — public, no login).
>
> **TL;DR: teeno products zinda hain. Do dataset IDs typos thi (jo MOSDAC
> HTTP 500 deta hai, isliye "product missing" lagta hai), teesra dataset ID
> bhi galat tha (asli ID unke paas supplied file se hi mila — bas search me
> likha hi nahi), aur teeno ke parser expectations guess kiye gaye variable
> names pe tethe. Plus ek 12-second timeout. Sab client-side the.**

## The live typo map (all verified 13 Sep 2026 via apios)

| Their repo registered ID (tier) | Live search | Real ID | Live proof |
|---|---|---|---|
| `E06SCT_L4_AWW6HOURLY` (S, blocked) | ❌ HTTP 500 | **`E06SCT_L4_AWV6HOURLY`** | 4756 files, ~7.9 MB, current |
| `E06SCT_L3_WV12` (S, blocked) | ❌ HTTP 500 | **`E06SCT_L3_WW12`** (= their own sample's dataset) | 1069 files, ~47 MB, current |
| `E06OCM_L3_LAC_CQ` (S, blocked) | ✅ **alive** | — (ID was right) | 157 files, daily, current |
| `E06SCT_L4_AWW` (A, disabled) | ❌ HTTP 500 | `E06SCT_L4_AWV` | 1330 files |
| `E06SCT_L4_AWW12km` (A, disabled) | ❌ HTTP 500 | `E06SCT_L4_AWV12km` | 393 files |
| (`E06SCT_L3_WV25` (A) — likely same WW typo, not probed) | ? | `E06SCT_L3_WW25`(?) | — |

**Why every typo looked like a product failure:** MOSDAC's apios returns
`HTTP 500 {"message":["Data unavailable for given parameters"]}` for an
unknown `datasetId` — not a 404. So a one-letter typo is
indistinguishable from "product unavailable" unless you probe the
correct spelling side by side. That is exactly how "blocked by product
evidence" conclusions got drawn.

## Failure 1 — `E06SCT_L4_AWW6HOURLY` → `LIVE_VERIFICATION_FAILED`

The chain, from their code:

1. **Live fetch**: `MosdacProvider.fetch()` searches
   `datasetId=E06SCT_L4_AWW6HOURLY` → apios **HTTP 500** (ID is a typo;
   real product is `E06SCT_L4_AWV6HOURLY`, AWV = Analyzed Wind Vector)
   → `raise_for_status()` raises → caught → `status: "unavailable",
   reason: "MOSDAC request failed: HTTPStatusError"`. That is the entire
   "Live request failed with an HTTP error".
2. **Sample rejection**: for this dataset `mosdac_parsers.py` expects a
   variable literally named **`wind_speed`** — the real product ships
   **`u`/`v`** (their own MOSDAC_INTEGRATION.md says the file has
   "`u` and `v` variables"). Even without the tripwire it would fail
   with `Required variable 'wind_speed' is missing`.
3. On top, a hard tripwire: any variable whose `long_name` is
   `"SIGMA0 VALUES"` → `raise "Sample is OSCAT3_GLO sigma0, not
   E06SCT_L4_AWW6HOURLY"`. The u/v arrays in this granule carry that
   (mis)label, so the file was rejected as the wrong product — and
   `test_mislabeled_analyzed_wind_sample_is_rejected` locks that in.

**Reality (live-verified):** `E06SCTL4AH_2026255_0000_25km_v1.0.0.nc` is
the newest granule OF THE CORRECT DATASET — apios returns that exact
identifier under `E06SCT_L4_AWV6HOURLY` (gId=18401334, summary
"Analyzed Winds are computed using Particle Filter Technique", 7 MB).
The `SIGMA0 VALUES` long_name on u/v is a MOSDAC PGE metadata quirk;
provenance is proven by the search record, and physical validity should
be decided by **value ranges after a fresh authenticated download**
(wind components ≈ ±40 m/s), not by a long_name veto. Their caution
wasn't unreasonable (MOSDAC has delivered mismatched order files
before) — but here the file was right and the ID + expectations were
wrong.

## Failure 2 — `E06OCM_L3_LAC_CQ` → `LIVE_VERIFICATION_FAILED`

Their note: "Live download was unavailable for the requested record; no
sample file was supplied."

- **The dataset is alive** — 157 files, daily through today, bbox
  68E–94E / 7N–24N, ~2.7 MB each, named
  `E06OCML3CQ_YYYYMMDD_01km_LAC_v1.0.0.nc`. Search works from a clean
  client with no params beyond `datasetId`.
- Their `"unavailable"` can only come from three client-side branches in
  `fetch()`:
  1. `"MOSDAC search returned no files."` — request params
     (startTime/endTime/boundingBox) that matched nothing; or
  2. the catch-all `"MOSDAC request failed: <Exception>"` — most
     plausibly **`httpx.ReadTimeout`/`ConnectTimeout`: the default
     `ORCA_PROVIDER_TIMEOUT_SECONDS` is 12 s for the whole
     search→gettoken→download chain**, and mosdac.gov.in routinely
     exceeds that; or
  3. download 401/404 → `"download_failed"`.
  Without their run log the exact branch is unknowable — but all three
  are client-side. The product itself was never the problem.
- **Double block even on success**: the parser hardcodes
  `variable_name = "water_quality"` for this dataset — a **guessed
  name**. Nobody had ever dumped a real CQ granule, so the real
  variables/flags/scaling are unknown; a successful download would have
  failed the parse with `Required variable 'water_quality' is missing`.

## Failure 3 — `E06SCT_L3_WV12` → `METADATA_VERIFICATION_BLOCKED`

1. **Live fetch**: `datasetId=E06SCT_L3_WV12` → **HTTP 500** — no such
   dataset. The supplied sample `E06SCTL3WW2026255_12km_v1.0.5.h5` is
   actually the newest granule of **`E06SCT_L3_WW12`** — "EOS-06
   Scatterometer L3 Product contains flagged wind vectors in global
   grid", 1069 files, ~47 MB, current (live-verified, gId=18400558).
   The swath sibling `E06SCT_L2B_WV12` (50,615 files, in-file 2D
   per-pixel lat/lon) sits **disabled in their own TIER_A_IDS**.
2. **The .h5 parser is a stub that always raises.** In
   `parse_product()`: after confirming the six
   `science_data/Ascending|Descending_*` wind variables exist, it
   *unconditionally* raises `"WV12 sample lacks latitude, longitude,
   time, scaling, and product metadata"`. Implementation.md admits it:
   "MOSDAC AWW/AWV or WV12 | Not implemented as a live fetcher | Parser
   recognition/documentation only". Only root + `science_data` were ever
   looked at — no recursive group walk, no attrs dump, no geolocation
   search. So "lacks geolocation/time/scaling" was a design decision of
   the stub, not an established fact about the file (fixed-grid L3
   products often define the grid in the product manual rather than
   in-file; the L2B swath product carries real 2D lat/lon + scaling
   in-file).

## Fix list for that backend (portable, evidence-gated)

1. **`mosdac_datasets.py`** — correct the IDs: `E06SCT_L4_AWV6HOURLY`,
   `E06SCT_L3_WW12` (and/or `E06SCT_L2B_WV12`), Tier-A `E06SCT_L4_AWV`,
   `E06SCT_L4_AWV12km`. Re-verify `E06SCT_L3_WV25`→`WW25`.
2. **`mosdac_parsers.py`** —
   - AWV6HOURLY: read `u`/`v`, `speed = hypot(u, v)`, meteorological
     direction from (u, v); replace the long_name tripwire with
     value-range validation (|u|,|v| ≤ 40 m/s, fill-masked cells → None).
   - LAC_CQ: dump ONE real granule before naming variables (the schema
     is unknown — that dump is the evidence step).
   - WW12/L2B: walk HDF5 recursively with h5py; for L2B swath read the
     2D packed lat/lon (scale_factor/add_offset) — this is exactly what
     ORCA-backend's `pipeline/extractors.py::extract_wind_swath` +
     `pipeline/deepdump.py` do; both are portable.
3. **`mosdac_provider.py`** — raise the 12 s timeout (60 s+ for
   download), pick the newest in-bbox entry instead of `entries[0]`,
   refresh the token once on 401.
4. **Re-run the live verification** with correct IDs; ORCA-backend's
   `tools/unblock_mosdac.py` produces per-granule evidence files
   (`docs/formats/*.md`) in one command and works with any MOSDAC
   account.

Honesty rule unchanged: enable only after a real granule parses with
real values. What changed is that the blocker was never the products —
it was four typos, a guessed schema, a stub parser, and a 12-second
timeout.
