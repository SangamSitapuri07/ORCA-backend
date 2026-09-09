# MOSDAC files received — 2026-09-02

> User successfully downloaded 5 NetCDF files from order Sep2026_189314.

## Files received

| # | Filename | Type | Size | Date | What it is |
|---|---|---|---|---|---|
| 1 | `E06SCTL4UI_2026244_25km_v1.0.5.nc` | NC | 4,068 KB (~4 MB) | 02-09-2026 | **Upwelling Index** ✅ |
| 2 | `JPSS2_VIIRS.20260831.L3m.DAY.CHL_chlor_a.9k...nc` | NC | 4,387 KB (~4 MB) | 02-09-2026 | VIIRS chlorophyll (from a different satellite!) |
| 3 | `JPSS2_VIIRS.20260831.L3m.DAY.CHL_chlor_a.4k...nc` | NC | 14,193 KB (~14 MB) | 02-09-2026 | VIIRS chlorophyll, higher resolution |
| 4 | `E06SCTL4AW_2026243_25km_v1.0.5 (1).nc` | NC | 52,772 KB (~52 MB) | 02-09-2026 | **Analyzed Winds** (duplicate?) |
| 5 | `E06SCTL4AW_2026243_25km_v1.0.5.nc` | NC | 52,772 KB (~52 MB) | 02-09-2026 | **Analyzed Winds** ✅ |

## Important observations

### 1. Date encoding is "Julian day"
- `2026244` = 2026, day 244 = **September 1, 2026**
- `2026243` = 2026, day 243 = **August 31, 2026**

(The form date "3/15/2026" we entered was probably overridden or
ignored — MOSDAC delivered the most recent data instead, which is
actually what we want for a demo.)

### 2. The order delivered MORE than we asked for
- We ordered: chlorophyll L4, wind L4, upwelling L4 (3 products)
- We got: upwelling + 2 chlorophyll files (from JPSS2/VIIRS) + 2 wind files
- The 2 chlorophyll files came from JPSS2 (a different satellite, NOAA's),
  not EOS-06. The 2 wind files look like duplicates (same size, same
  name with " (1)" suffix).
- This is normal — MOSDAC's order system may add related products
  automatically or the form delivered default companion files.

### 3. EOS-06 chlorophyll (E06OCM_L4_AC) is MISSING
- We ordered it but it's not in the list
- We got JPSS2/VIIRS chlorophyll instead, which is a different satellite
- This might be because the form had different defaults, or the order
  was split. We may need to re-order E06OCM_L4_AC separately.

### 4. File format
All files are **NetCDF** (`.nc`) — our parser handles this.

## What we have that works

✅ Wind data (52 MB) — can parse and use
✅ Upwelling index (4 MB) — can parse and use
✅ Chlorophyll (from JPSS2/VIIRS, 4 MB and 14 MB versions) — different
  source than what we planned, but still real chlorophyll data

## What we should still get

❌ EOS-06 OCM L4 chlorophyll — re-order separately

## Action items

1. **Tell the user**: re-order E06OCM_L4_AC (Analyzed Chlorophyll from
   EOS-06 specifically) to get the ISRO satellite chlorophyll we
   originally wanted
2. **For now**: we can build the pipeline using the files we have
   - Wind + Upwelling from EOS-06 (exactly what we wanted)
   - Chlorophyll from JPSS2/VIIRS (different source, same data type)

## File naming convention learned

MOSDAC filename pattern: `E06<TYPE>L4<NAME>_<YYYYDDD>_<RES>km_v<VERSION>.nc`
- `E06` = EOS-06 satellite
- `SCT` = scatterometer
- `L4` = processing level 4
- `UI` / `AW` = product short name (Upwelling Index / Analyzed Winds)
- `2026243` = date as Julian day (year + day-of-year)
- `25km` = grid resolution
- `v1.0.5` = product version

## Next step

Write the parser for NetCDF files matching this naming pattern.
We can build + test on the 3 unique files we have:
- E06SCTL4UI_2026244_25km_v1.0.5.nc (upwelling)
- E06SCTL4AW_2026243_25km_v1.0.5.nc (wind)
- JPSS2_VIIRS.20260831.L3m.DAY.CHL_chlor_a.4k...nc (chlorophyll)
