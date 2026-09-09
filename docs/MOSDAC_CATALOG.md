# MOSDAC Catalog — what we found

> Screenshots captured by user on 2026-09-02 from
> https://mosdac.gov.in/catalog/satellite.php while logged in as Sangam Sitapuri.

## Confirmed structure

- **Datasource: EOS-06** (= OCEANSAT-3, ISRO's current operational ocean satellite)
- **Two Category options on EOS-06**: SCATTEROMETER and OCM
- All SCATTEROMETER products cover **2024-06-01 → 2026-09-02** (current!)

## 🔥 Best finds for PS 176

### `E06SCT_L4_AWV` (row 14) — **the crown jewel for our "is it safe?" use case**
> "Analyzed Winds are computed using optimal interpolation. The wind
> derived products and fluxes are computed based on COREv3.0 bulk
> algorithms." — **L4, DAILY, 2023-02-09 → 2026-09-01**

This is **the most useful wind product for us.** L4 means ISRO already
cleaned + gap-filled it. Daily resolution. **3+ years of historical
data + current daily updates.** For a "is it safe today?" question,
this is exactly what we want.

### `E06SCT_L4_AWV12km` (row 15) — **same as above, higher resolution**
> "Analyzed Winds (12.5 km) ... COREv3.0 bulk algorithms." — **L4, DAILY, 2025-06-24 → 2026-09-01**

12.5 km cells instead of 25 km. Better for coastal fishing zones.
Tradeoff: only ~14 months of data, no historical depth.

### `E06SCT_L4_AWV6HOURLY` (row 16) — **6-hourly winds**
> "Analyzed Winds are computed using Particle Filter Technique" — **L4, 6 HOURLY, 2023-02-09 → 2026-09-02**

Use this for the "tomorrow morning" type questions — has the temporal
resolution for short-term forecasts.

### `E06SCT_L2B_WV12` / `E06SCT_L2B_WV25` (rows 4-5) — **raw wind vectors**
L2B swatch-grid wind vectors. Lower-level but more recent (2024-06-01
→ 2026-09-02). Use these if L4 is too aggregated.

### `E06SCT_L4_UI` (row 30) — **🎯 Upwelling index over Indian Ocean**
> "Upwelling index over indian ocean" — **L4, DAILY, 2023-02-09 → 2026-09-01**

**This is huge.** Upwelling = nutrient-rich cold water rising to the
surface = prime fishing grounds. INCOIS itself uses upwelling indices
for PFZ forecasts. Having this directly is a real win.

## Skip these (not useful for PS 176)

| Row | datasetId | Why skip |
|---|---|---|
| 1-3, 8-13 | `E06SCT_L1B_SIG`, `L2A_SIG*`, `L3_SIG*` | Raw sigma-0 backscatter — needs processing, no direct use |
| 6-7, 28-29 | `E06SCT_L3_GS_*`, `E06SCT_L4_SI_NP`, `E06SCT_L4_SM_NP_DLY` | Sea ice / Greenland / North Pole — irrelevant to Indian coast |
| 17-27 | `E06SCT_L4_BT_*`, `E06SCT_L4_GAM_*`, `E06SCT_L4_SIG_*` | Land surface products — not ocean |

## OCEAN_COLOR (OCM) — confirmed 2024-2026 (already in earlier doc)

Best for PS 176:

| datasetId | What it gives | Level | Why |
| --- | --- | --- | --- |
| `E06OCM_L4_AC` | Analyzed Chlorophyll + MOM5/TOPAZ assimilation | L4 | **PFZ**, productivity |
| `E06OCM_L2C_LAC_OC` | Inherent Optical Properties (Rrs) | L2 | For chlorophyll derivation |
| `E06OCM_L2C_LAC_PS` | Phytoplankton size class | L2 | What species are present |
| `E06OCM_L2C_LAC_GA` | CDOM at 412nm | L2 | Water clarity / eutrophication |
| `E06OCM_L2C_LAC_PR` | PAR | L2 | Light for plankton |
| `E06OCM_L3_LAC_FL` | 8-day nFLH | L3 | Algal blooms |
| `E06OCM_L3_LAC_PQ` | Daily coastal water quality | L3 | Coastal composite |
| `E06OCM_L3_LAC_PC` | 8-day Particulate Organic Carbon | L3 | Ocean biogeochemistry |

## SST — confirmed NOT in MOSDAC EOS-06 catalog

User confirmed: the OCM table has 12 products, none of which is
SST / sea surface temperature. The complete OCM list:

| # | datasetId | What it gives |
|---|---|---|
| 1 | `E06OCM_L2C_LAC_AD` | Aerosol Optical Depth over Land |
| 2 | `E06OCM_L2C_LAC_EV` | Enhanced Vegetation Index |
| 3 | `E06OCM_L2C_LAC_GA` | CDOM at 412nm |
| 4 | `E06OCM_L2C_LAC_OC` | Inherent Optical Properties |
| 5 | `E06OCM_L2C_LAC_PR` | Photosynthetically Active Radiation |
| 6 | `E06OCM_L2C_LAC_PS` | Phytoplankton size class |
| 7 | `E06OCM_L2C_LAC_SR` | Land Surface Reflectance |
| 8 | `E06OCM_L3_LAC_AD` | Daily AOD over Land |
| 9 | `E06OCM_L3_LAC_CQ` | Daily coastal water quality (Indian subcontinent) |
| 10 | `E06OCM_L3_LAC_FL` | 8-day nFLH |
| 11 | `E06OCM_L3_LAC_PC` | 8-day Particulate Organic Carbon |
| 12 | `E06OCM_L4_AC` | Analyzed Chlorophyll (MOM5 + TOPAZ) |

**Decision: use Open-Meteo for SST.**
- Free, no key
- Hourly resolution (better than daily)
- Covers global ocean
- Already integrated in our prototype

## What we still need to confirm

## Final recommended datasetId list

| Use case | datasetId | Level | Resolution |
| --- | --- | --- | --- |
| PFZ (where to fish) | `E06OCM_L4_AC` | L4 | daily |
| Productivity analysis | `E06OCM_L2C_LAC_OC` + `E06OCM_L2C_LAC_PS` | L2 | scene |
| Upwelling / cold water | `E06SCT_L4_UI` | L4 | daily |
| Wind safety (today) | `E06SCT_L4_AWV` | L4 | daily |
| Wind safety (6-hour) | `E06SCT_L4_AWV6HOURLY` | L4 | 6-hourly |
| Wind (high-res) | `E06SCT_L4_AWV12km` | L4 | 12.5 km daily |
| SST | Open-Meteo (fallback) | — | hourly |

That's **7 real ISRO products + 1 free fallback**. More than enough
for a complete PS 176 demo.

---

## ✅ VERIFIED LIVE — 3 Sep 2026 (Arena agent + zwiter07 account)

**Auth (machine door):**
- token: `POST https://mosdac.gov.in/download_api/gettoken` — JSON `{"username","password"}` → `{access_token, refresh_token}`
- refresh: `POST /download_api/refresh-token`
- download: `GET /download_api/download?id=<record_id>` (Bearer)
- search: `GET /apios/datasets.json` — **NO login needed**
- DO NOT use Keycloak SSO programmatically (browser-only; lockout after repeated fails). FIXED in `pipeline/mosdac_auth.py`.

**Query formats:** `datasetId=<id>&startTime=YYYY-MM-DD&endTime=YYYY-MM-DD&boundingBox=minLon,minLat,maxLon,maxLat&count<=100` · daily limit 5000 files/user · bbox Gujarat: `66.0,18.0,72.5,23.5`

**Datasets verified live:**
| datasetId | kya | count proof |
|---|---|---|
| `E06OCM_L2C_LAC_OC` | EOS-06 (Oceansat-3) OCM ocean colour = **chlorophyll** | 71 files — Gujarat box, 25Aug–2Sep 2026 |
| `3RIMG_L2B_SST` | INSAT-3DR **SST** | 352 files — Gujarat box, 25Aug–2Sep 2026 |
| `E06SCT_L2B_WV12` / `_WV25` | SCAT-3 **ocean winds** | catalog confirmed |

**Catalog browser (public):** https://mosdac.gov.in/catalog-app/satellite.php  (satellites: EOS-06=id22, EOS-08=33, OCEANSAT-2=9, SCATSAT-1=15, INSAT-3DR=14, INSAT-3DS=24)
**Official manual:** https://mosdac.gov.in/downloadapi-manual · client: https://mosdac.gov.in/software/mdapi.zip
