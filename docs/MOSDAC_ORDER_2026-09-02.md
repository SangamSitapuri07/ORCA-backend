# MOSDAC Order Confirmation — 2026-09-02

> Email received by Sangam Sitapuri confirming the 3-product order.

## Order details

- **Request ID**: `Sep2026_189314`
- **Order Date**: 02-Sep-2026
- **Order Completed Date**: 02-Sep-2026 (same day — fast!)
- **Total Products**: 5 (note: 5 not 3 — we ordered 3 but the order
  is split into 5 file granules. Could be one per day + one image.)

## Download options (3 ways)

### 1. SSO web download (easiest, recommended)
URL: https://mosdac.gov.in/sso-download
- Log in with the same MOSDAC credentials
- See your order, click each file to download via browser
- No extra software needed

### 2. Interactive Python Notebooks (MOSAIC)
URL: https://mosdac.gov.in/mosaiclab
- Run Python in MOSDAC's Jupyter environment
- Can read our files directly without downloading
- Useful for quick exploration

### 3. SFTP bulk download (advanced)
- Server: `download.mosdac.gov.in`
- Port: 22
- Use FileZilla (Windows/Mac/Linux GUI) or `sftp` command (Linux/Mac)
- Username/password = same as MOSDAC account

## Important: 5-day download window

> "Ordered products will be available only for 5 days for download."

So we have until **2026-09-07** to grab the files.

## Files we expect to receive

Based on the 3 datasetIds ordered:

| datasetId | Expected filename pattern | Expected size |
| --- | --- | --- |
| `E06OCM_L4_AC` | `E06OCM_L4_AC_20260315.nc` (or similar) | 1-10 MB |
| `E06SCT_L4_AWV` | `E06SCT_L4_AWV_20260315.nc` | 1-10 MB |
| `E06SCT_L4_UI` | `E06SCT_L4_UI_20260315.nc` | 1-10 MB |

Plus possibly PNG/JPEG preview images.
