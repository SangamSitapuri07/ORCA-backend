# MOSDAC Order Form — what to fill in

> Reference for Sangam when ordering the 3 products. Saved 2026-09-02.

## The form fields (left to right, top to bottom)

### 1. **Version**: `v1.0.1`
Default. Leave it. (If a newer version appears, use the latest.)

### 2. **Start Date**: pick a date
End Date: same date
- For daily products (chlorophyll, wind): **Start = End = one day** (you get that day's file)
- The form says dates must be between **20-06-2023** and **30-03-2026**

**Recommended date: `2026-03-15`** (about 6 months old — easy to verify, well-formed)

### 3. **Format**: **NetCDF** ✅
The other option might be HDF5, but NetCDF is more common and our parser handles it.

### 4. **Media**: **Both Products & Image** (already selected, leave it)
- "Products Only" = just the data file
- "Browse Images Only" = just a preview PNG
- "Both" = the data + a preview image (useful for our web app later)

### 5. Click **Submit** / **Add to Cart**

## The 3 to order, in this order

| # | datasetId | Category tab | Date |
|---|---|---|---|
| 1 | `E06OCM_L4_AC` | OCM (Analyzed Chlorophyll) | 2026-03-15 |
| 2 | `E06SCT_L4_AWV` | SCATTEROMETER (Analyzed Winds) | 2026-03-15 |
| 3 | `E06SCT_L4_UI` | SCATTEROMETER (Upwelling Index) | 2026-03-15 |

## What happens after you submit

1. MOSDAC adds the order to your cart
2. You go to **Cart** (🛒 icon top right) and **Confirm**
3. You get an email when files are ready (could be minutes, could be hours)
4. Download via SFTP (they'll give creds) or web UI
5. Save the files anywhere on your computer

## When files arrive

Tell me:
- Filename of each (e.g., `E06OCM_L4_AC_20260315.nc`)
- Size of each (e.g., 3.2 MB)

I won't need the actual files — just the names tell me what schema to expect.
