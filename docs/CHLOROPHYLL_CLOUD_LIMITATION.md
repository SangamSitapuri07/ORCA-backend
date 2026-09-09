# Chlorophyll Extraction — Cloud-Masking Limitation

> Discovered 2026-09-02 while debugging why all Indian Ocean points
> returned NaN for chlorophyll.

## The finding

The JPSS2/VIIRS Level-3 Standard Mapped Image (SMI) for 2026-08-31 has
**only 11.5% valid cells globally**. The Arabian Sea and Bay of Bengal
are essentially **100% NaN** in the monsoon month, with valid data
appearing only in cloud-free regions (Caribbean, Coral Sea, open Pacific).

This is **not a bug** in our pipeline. It's a **physical limitation
of optical remote sensing during the Indian summer monsoon**.

## Why

| Cause | Effect |
|---|---|
| Heavy cloud cover (Jun-Sep) | ~90% of Arabian Sea pixels masked |
| Sun glint (high sun angle) | More masking in tropical waters |
| Single-day file | No way to fill cloud gaps from the same day |
| OCI algorithm flags low-quality pixels | Additional masking |

## Diagnostic that proved this

```
$ python -m pipeline.where_is_data JPSS2_VIIRS.20260831.L3m.DAY.CHL.chlor_a.9km.NRT.nc

Valid cells: 1,077,055 / 9,331,200 (11.5%)

Location                  Val      NaN count 5x5
Indian Ocean (Mumbai)     NaN      121/121  ← entire 5x5 region masked
Bay of Bengal             NaN      121/121
Arabian Sea central       0.2640   102/121  ← some open ocean data
Equatorial Pacific        NaN      121/121
Caribbean                 0.0560   5/121    ← clear-sky open ocean
```

## Implications for ORCA

1. **Real-time chlorophyll** is unreliable in monsoon season over India.
   The "fresh data" problem isn't data freshness — it's cloud coverage.

2. **Temporal compositing** is essential. A 7-day or 30-day composite
   fills cloud gaps. The NASA OBPG publishes 8-day and monthly composites
   alongside the daily files.

3. **Alternative data sources** during monsoon:
   - **INCOIS** (Indian National Centre for Ocean Information Services)
     — has its own chlorophyll processing chain
   - **Multi-day composites** from MOSDAC
   - **Modelled chlorophyll** from numerical ocean models

4. **Wind and upwelling** are NOT affected by clouds (scatterometer
   is a microwave sensor). The MOSDAC EOS-06 files we have show
   consistent wind data even where chlorophyll is masked.

## What we changed in the code

The chlorophyll extractor now searches 10x10 (~100 km radius) around
the request point and returns the nearest valid cell. This handles
**partial cloud coverage** (a few cells masked) but cannot help when
**the entire region is masked for that day** — which is what happens
in monsoon season over coastal India.

## Recommended next steps

1. Order a **7-day or monthly composite** from MOSDAC
   (datasetId likely `E06OCM_L3B_*` or similar)
2. Or use **INCOIS daily chlorophyll** when available
3. For now, the platform should gracefully degrade: "chlorophyll data
   unavailable for this date due to cloud cover" + still show wind +
   upwelling
