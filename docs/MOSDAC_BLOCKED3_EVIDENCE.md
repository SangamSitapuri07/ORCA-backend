# The "blocked three" — evidence + fix plan (2026-09-13)

> Verdict under review (2026-09-12): `E06SCT_L4_AWW6HOURLY`,
> `E06OCM_L3_LAC_CQ`, `E06SCT_L3_WV12` disabled pending "exact official
> product files/metadata and successful authenticated downloads".
>
> **Result of live re-verification: the block was built on two wrong
> dataset IDs and one misread file. All three products are real, live and
> downloadable. The parsing gap is closed in code (this commit). What
> remains is one command on the machine with the MOSDAC creds.**

## 1. Live evidence — MOSDAC OpenSearch (`/apios/datasets.json`), 13 Sep 2026

Search is public (no login — confirmed by MOSDAC's own
[download API manual](https://mosdac.gov.in/downloadapi-manual)).

| Searched ID | Result | Meaning |
|---|---|---|
| `E06SCT_L4_AWW6HOURLY` | **HTTP 500** "Data unavailable for given parameters" | ❌ the ID does not exist — **typo** (double-W) |
| `E06SCT_L4_AWV6HOURLY` | ✅ **4756 files, 37 762 MB**, current through 2026-09-12 | the real 6-hourly analyzed-wind dataset |
| `E06OCM_L3_LAC_CQ` | ✅ **157 files, 428 MB**, daily through 2026-09-12 | the coastal water-quality product is alive |
| `E06SCT_L3_WV12` | **HTTP 500** "Data unavailable for given parameters" | ❌ no such dataset — **wrong level** |
| `E06SCT_L2B_WV12` | ✅ **50 615 files, 776 GB**, current through 2026-09-12 | the real L2B wind-vector swath dataset |

### The three real products, exactly as MOSDAC serves them

**`E06SCT_L4_AWV6HOURLY`** — "Analyzed Winds are computed using Particle
Filter Technique", L4, 6-hourly, global.
- Filenames: `E06SCTL4AH_<YYYYDDD>_<HHMM>_25km_v1.0.0.nc`
  (e.g. `E06SCTL4AH_2026255_0000_25km_v1.0.0.nc`, `…_2026254_0012_…`)
- **~7.9 MB per file** (gId=18401334 → `totalSizeMB: 7`), global bbox.
- 🔑 **The file the user supplied earlier IS this dataset's newest
  granule** — the search API returns that exact identifier. The old
  verdict called it "OSCAT3_GLO_25km with SIGMA0 VALUES, not the
  AWW6HOURLY wind product". That was an ID typo (AWW→AWV) plus reading
  the file's `title` attribute (a sensor/grid label) as the product
  identity. If the granule contains `U`/`V` alongside sigma-0 fields it
  is a *legitimate* analyzed-wind file — the new deep dump settles this
  from the file itself, not from a label.

**`E06OCM_L3_LAC_CQ`** — "Daily composite of coastal water quality for
coastal regions of Indian subcontinent", L3, daily, 1 km LAC.
- Filenames: `E06OCML3CQ_<YYYYMMDD>_01km_LAC_v1.0.0.nc`
- ~2.7 MB per file, bbox 68E–94E / 7N–24N, updated today.
- The old "live search/download did not provide an usable product" does
  not reproduce: search returns today's composite. No sample file was
  ever pulled — that's the only gap. Variables/flags/scaling are unknown
  *to us*, not unknowable: one download + `deepdump` documents them.

**`E06SCT_L2B_WV12`** — "EOS-06 Scatterometer L2B Product contains
flagged wind vectors in swath grid", L2B, 12.5 km swath.
- Filenames: `E06SCTL2B<YYYYDDD>_<revStart>_<revEnd>_<NS|SN>_12km_2026-255T10-54-49_v1.0.5.h5`
- ~15 MB per file, per-revolution bboxes (real footprint filtering works).
- 🔑 The old verdict: "HDF5 contains wind arrays and quality flags, but
  lacks usable latitude, longitude, time, scaling". **Swath products keep
  geolocation as 2D per-pixel arrays (often packed int16 +
  scale_factor), usually in a subgroup — not as 1D grid coordinates.**
  Our xarray-only parser showed nothing in `.coords` and we concluded
  the data was missing. It wasn't; the reader was grid-only.

## 2. What is already fixed in code (this commit)

| Fix | File | Proof |
|---|---|---|
| Correct dataset IDs registered (+ India-coast bbox) | `pipeline/mosdac_auth.py` | constants citing the live counts above |
| `AH` product + 6-hourly `HHMM` cycle folded into the date | `pipeline/parser.py` | `test_filename_ah_6hourly_cycle_time` |
| **8-digit date bug**: `\d{6,7}` read `20260912` as Julian `2026091` → 1 Apr; now 8-digit YYYYMMDD tried first | `pipeline/parser.py` | `test_filename_cq_8_digit_date_regression` |
| `L2B` level + embedded Julian date in the head block → product `WV` | `pipeline/parser.py` | `test_filename_l2b_swath_head` |
| HDF5 **group-aware walk** (h5py, recursive) merged into the variable inventory — geolocation in subgroups is now visible | `pipeline/parser.py` | `test_wv12_swath_detected_with_group_variables` |
| Swath detection on `ParsedFile` (`pf.swath`, `swath_lat/lon`) | `pipeline/parser.py` | same |
| **`extract_wind_swath()`** — nearest-pixel search over 2D packed lat/lon, scale/offset + fill decoding, U/V or speed/dir, raw quality flag reported (never masked on guessed semantics) | `pipeline/extractors.py` | `test_wv12_swath_wind_extraction`, `test_wv12_swath_fill_pixel_is_none_not_fabricated` |
| **`pipeline/deepdump.py`** — evidence-grade dump: sha256, global attrs, every variable with full attrs + decoded min/max/%valid, and a parseability checklist (`WIND-PARSE-READY` grid/swath vs `NOT-WIND`) | new | `test_deepdump_*` |
| **`tools/unblock_mosdac.py`** — the one-command unblock (below) | new | used below |

Sigma-0 red herring: a wind file that *also* carries `SIGMA0_VALUES` and
a `title` of `OSCAT3_GLO_25km` still extracts wind when `U`/`V` exist —
`test_ah_grid_parses_and_extracts_wind_despite_sigma0`.

## 3. The remaining step — one command, on the laptop with the creds

`.env` at repo root (never committed):

```
MOSDAC_USERNAME=<your mosdac user>
MOSDAC_PASSWORD=<your mosdac password>
```

Then:

```bash
# 3a. prove the datasets are live — NO creds needed:
python tools/unblock_mosdac.py --search-only

# 3b. the real thing: search → download 1 newest granule per dataset
#     (size-guarded, magic-byte-checked) → deep evidence dump to
#     docs/formats/*.md + data/mosdac_probe/*.json → wind extraction
#     attempted at Veraval & Kochi offshore:
python tools/unblock_mosdac.py

# 3c. the AH file from the old order — no network needed:
python tools/unblock_mosdac.py --local "E06SCTL4AH_2026255_0000_25km_v1.0.0.nc"
```

Each step prints real reasons when it fails — nothing is invented. The
`docs/formats/*.md` files are small and meant to be committed: that IS
the "exact official product metadata" the block was waiting for.

## 4. After the evidence — activation checklist

For each dataset, gate on what the dump actually shows:

1. **AWV6HOURLY** — if `U`/`V` + 1D lat/lon present → wire
   `extract_wind` (already works). Add a `pipeline/` getter modelled on
   `mosdac_ocm.py` (search newest in-bbox → download → extract), then
   surface in the weather agent with the 6-hourly cycle time in the
   message. If the real file turns out to be genuinely sigma-0-only
   (MOSDAC has delivered mismatched orders before — see
   `MOSDAC_FILES_RECEIVED.md`), the dump proves it and we escalate to
   MOSDAC support with the sha256 in hand.
2. **LAC_CQ** — the dump lists the real variable names, flags and
   scaling; then write `extract_water_quality()` (same pattern as
   chlorophyll) and gate the ecology agent on it.
3. **WV12 L2B** — `extract_wind_swath` is ready; wire the satellite
   agent to prefer L4 analyzed winds and use L2B for the "latest
   overpass" freshness story, always reporting the quality flag.

Until those dumps exist, the datasets stay disabled — the honesty rule
is unchanged. What changed: the blocker is now a 10-minute errand, not a
mystery.

## 5. Sister-repo postscript (13 Sep 2026)

The same "blocked three" verdict also lives in
`prabhbani/ORCA-SIH-2026`'s backend (`backend/mosdac_datasets.py` etc.).
Root causes there: the two typo IDs above, a third wrong ID for the
supplied h5 (its real dataset is `E06SCT_L3_WW12`, 1069 live files),
guessed variable names (`wind_speed`, `water_quality`), an always-raise
HDF5 stub parser, and a 12 s provider timeout. Full chain-by-chain
analysis with code references: **[SIH2026_BACKEND_DIAGNOSIS.md](SIH2026_BACKEND_DIAGNOSIS.md)**.
