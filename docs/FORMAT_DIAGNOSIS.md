# File format diagnosis — 2026-09-02

> User ran the magic bytes check on the EOS-06 upwelling file.

## The diagnosis

First 16 bytes (hex): `43 44 46 01 00 00 00 00 00 00 00 0a 00 00 00 04`

ASCII: `CDF` followed by 0x01 (version byte), then zeros, then `0a` (10), then `04`.

### What this means

`CDF\x01` = **NetCDF-3 classic format** (or "NetCDF Classic").

This is the **older** NetCDF format from the 1990s, before HDF5. Common in
older satellite data products. My initial detector was too strict (it
checked for the HDF5-based NetCDF-4 magic `89 48 44 46`, not for the
plain `CDF` header of NetCDF-3).

## Fix

xarray's `open_dataset()` should handle both formats automatically. The
reason `pipeline/parser.py` reported "unknown" is that my magic-byte
detector saw `\x89HDF\r\n\x1a\n` (HDF5/NetCDF-4) and the file's first
bytes are different (NetCDF-3). The detector needs a NetCDF-3 branch.

## Affected files

Both EOS-06 files are likely NetCDF-3:
- `E06SCTL4UI_2026244_25km_v1.0.5.nc` (upwelling, 4 MB)
- `E06SCTL4AW_2026243_25km_v1.0.5.nc` (wind, 52 MB)

The JPSS2/VIIRS file parsed fine because it's NetCDF-4 / HDF5 based.

## Next step

Update the parser to:
1. Detect NetCDF-3 magic (`CDF\x01` or `CDF\x02`)
2. Try opening as NetCDF-3 first, then fall back to NetCDF-4
3. Re-run the inspect command

The user can also bypass the format detection by just calling xarray
directly on the file.
