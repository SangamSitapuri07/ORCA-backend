"""Quick format scanner — identifies what kind of file we have by looking
at the magic bytes and structure. Use this when 'unknown' is reported.

Run:
    python -m pipeline.scan_format path/to/file

It prints:
  - First 16 bytes as hex
  - Common file-format magic byte matches
  - If it looks like HDF5/NetCDF, lists the top-level objects
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path


# Known magic byte signatures for scientific data formats
MAGIC_SIGNATURES = [
    # (description, signature bytes, offset)
    ("NetCDF classic (v1)", b"\x89HDF\r\n\x1a\n", 0),  # actually HDF5
    ("NetCDF-3 / HDF4-ish", b"CDF", 0),
    ("GRIB1", b"GRIB", 0),
    ("GRIB2", b"GRIB", 0),
    ("HDF5 v0", b"\x89HDF\r\n\x1a\n", 0),
    ("HDF4 SD", b"\x0e\x03\x13\x01", 512),  # offset 512
    ("HDF4 vdata", b"NC\x00\x00", 0),
    ("HDF4 generic", b"\x0e\x03", 0),
    ("NetCDF-4 = HDF5", b"\x89HDF\r\n\x1a\n", 0),
    ("BUFR", b"BUFR", 0),
    ("GeoTIFF (little-endian)", b"II\x2a\x00", 0),
    ("GeoTIFF (big-endian)", b"MM\x00\x2a", 0),
    ("PNG", b"\x89PNG\r\n\x1a\n", 0),
    ("JPEG", b"\xff\xd8\xff", 0),
    ("GZIP", b"\x1f\x8b", 0),
    ("ZIP / NetCDF-4 / DOCX", b"PK\x03\x04", 0),
    ("BZ2", b"BZh", 0),
    ("7-zip", b"\x37\x7a\xbc\xaf\x27\x1c", 0),
    ("TAR", b"ustar", 257),
]


def scan(path: str | Path) -> None:
    p = Path(path)
    if not p.exists():
        print(f"❌ Not found: {p}")
        return

    size_mb = p.stat().st_size / (1024 * 1024)
    print(f"📁 {p.name}  ({size_mb:.2f} MB)")
    print()

    # Read first 1KB to inspect
    with open(p, "rb") as f:
        first_kb = f.read(1024)
        # Also read at offset 512 (HDF4 SD signature location)
        f.seek(512)
        at_512 = f.read(16)
        f.seek(257)
        at_257 = f.read(5)

    # Print first 32 bytes as hex
    head = first_kb[:32]
    print(f"First 32 bytes (hex):")
    print("   " + " ".join(f"{b:02x}" for b in head))
    print(f"First 32 bytes (ascii, . = non-printable):")
    printable = "".join(chr(b) if 32 <= b < 127 else "." for b in head)
    print(f"   {printable}")
    print()

    # Check magic bytes
    print("Format signature matches:")
    any_match = False
    for desc, sig, offset in MAGIC_SIGNATURES:
        if offset == 0:
            haystack = first_kb
        elif offset == 257:
            haystack = at_257 + first_kb[:16]
        elif offset == 512:
            haystack = at_512 + first_kb[:16]
        else:
            haystack = first_kb[max(0, offset):]
        if haystack[:len(sig)] == sig:
            print(f"   ✅ {desc}")
            any_match = True
    if not any_match:
        print("   ❓ No common format signature matched")
    print()

    # If looks like HDF5, try to peek at structure
    if first_kb[:4] == b"\x89HDF":
        print("Looks like HDF5. Trying to introspect...")
        try:
            import h5py
            with h5py.File(p, "r") as f:
                print(f"   Root attributes: {list(f.attrs.keys())[:10]}")
                print(f"   Top-level groups/datasets ({len(f.keys())} total):")
                for k in list(f.keys())[:20]:
                    obj = f[k]
                    if isinstance(obj, h5py.Dataset):
                        print(f"     • {k}  shape={obj.shape}  dtype={obj.dtype}")
                    else:
                        print(f"     • {k}/  (group)")
        except Exception as e:
            print(f"   ❌ h5py failed: {e}")
        return

    # If looks like NetCDF-3 (starts with CDF)
    if first_kb[:3] == b"CDF":
        print("Looks like NetCDF-3 classic format.")
        try:
            import xarray as xr
            ds = xr.open_dataset(p)
            print(f"   Variables: {list(ds.data_vars)[:10]}")
            print(f"   Coords: {list(ds.coords)[:5]}")
            ds.close()
        except Exception as e:
            print(f"   ❌ xarray failed: {e}")
        return

    # Otherwise: look for ASCII text — might be header info in some formats
    ascii_text = "".join(chr(b) if 32 <= b < 127 else " " for b in first_kb)
    print("First 1KB as ASCII (whitespace = non-printable):")
    print("   " + ascii_text[:500])
    print()

    # Final suggestion
    print("💡 If none of the above matches, please paste this output in chat.")
    print("   Also useful: install `file` command-line tool and run:")
    print(f"   file {p}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.scan_format path/to/file")
        sys.exit(1)
    scan(sys.argv[1])
