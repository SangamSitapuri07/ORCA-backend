"""NetCDF / HDF5 parser for MOSDAC files.

We support two file types because MOSDAC publishes both:

  * **NetCDF4** (`.nc`) — most L3/L4 ocean colour + wind products
  * **HDF5**   (`.h5`, `.hdf5`) — some L2 / scatterometer products

The parser is deliberately *defensive* — it never crashes on weird
metadata, missing attributes, or unexpected variable names. It always
returns a `ParsedFile` with whatever it could extract plus a `warnings`
list so the caller knows what to look at.

Naming convention learned from real MOSDAC files (Sep 2026):
    E06SCTL4UI_2026244_25km_v1.0.5.nc
    └──┘└┘└┘└┘ └──┘ └──┘ └────┘
     │   │ │ │   │    │     └─ version (e.g. v1.0.5)
     │   │ │ │   │    └─ grid resolution (e.g. 25km, 4k, 9k)
     │   │ │ │   └─ date as Julian day (2026244 = Sep 1, 2026)
     │   │ │ └─ product short name (UI, AW, AC, OCN, etc.)
     │   │ └─ processing level (L1B, L2A, L2B, L3, L4)
     │   └─ instrument (SCT = scatterometer, OCM = ocean colour monitor)
     └─ satellite (E06 = EOS-06/OCEANSAT-3, O2 = OCEANSAT-2)

For NOAA JPSS2/VIIRS files the pattern is different:
    JPSS2_VIIRS.20260831.L3m.DAY.CHL_chlor_a.4km.nc
"""
from __future__ import annotations

import re
import warnings as _warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Patterns for MOSDAC + common scientific satellite file names.
#
# Real MOSDAC files look like:  E06SCTL4UI_2026244_25km_v1.0.5.nc
# So the satellite (E06), instrument (SCT), level (L4), and product
# (UI) are *concatenated* with no separator. We split that block by
# trying every known product code in the right place — much more
# reliable than regex guessing.

# Known product short codes we've seen in MOSDAC filenames.
# If we find a new one, add it here and the parser will pick it up.
_KNOWN_PRODUCTS = {
    "UI", "AW", "AWV", "AWV12KM", "AWV6HOURLY", "AC", "OC", "GA", "PR",
    "PS", "SR", "AD", "EV", "CQ", "FL", "PC", "BT", "GAM", "SIG", "GS",
    "WV", "HWV", "DAILYAWV", "AWV50",
}

# Satellite prefixes we know about
_KNOWN_SATELLITES = {"E04", "E06", "O2", "O3", "INS3DR", "INS3DS", "JPSS1", "JPSS2"}

# Instrument short codes
_KNOWN_INSTRUMENTS = {"SCT", "OCM", "VIIRS", "MODIS", "RAD", "IMG", "LID"}


def _parse_mosdac_block(name: str) -> dict | None:
    """Parse the leading 'E06SCTL4UI' style block by trying known codes.

    Strategy: try every (sat, inst, level, product) combination that
    matches the prefix, picking the longest one that succeeds. This is
    how a human would read it: "I know UI is a product, so the rest
    must split that way."
    """
    result = {
        "satellite": None,
        "instrument": None,
        "processing_level": None,
        "product_name": None,
    }
    upper = name.upper()
    head = upper.split("_")[0]  # everything before the first underscore

    # 1. Find satellite prefix
    sat = None
    for s in sorted(_KNOWN_SATELLITES, key=len, reverse=True):
        if head.startswith(s):
            sat = s
            break
    if sat is None:
        # Fallback: anything like E + digits
        m = re.match(r"^(E\d+)", head)
        if m:
            sat = m.group(1)
    if sat is None:
        return None
    result["satellite"] = sat
    rest = head[len(sat):]

    # 2. Find instrument (optional)
    inst = None
    for i in sorted(_KNOWN_INSTRUMENTS, key=len, reverse=True):
        if rest.startswith(i):
            inst = i
            break
    if inst:
        result["instrument"] = inst
        rest = rest[len(inst):]

    # 3. Find processing level — must be L followed by 1-2 chars (digit
    #    optionally followed by a letter like 1B, 2A, 2B, 3M)
    m = re.match(r"^L(\dm?)", rest)
    if not m:
        return None
    result["processing_level"] = "L" + m.group(1)
    rest = rest[m.end():]

    # 4. Find product — try known codes longest-first
    for p in sorted(_KNOWN_PRODUCTS, key=len, reverse=True):
        if rest.startswith(p):
            result["product_name"] = p
            return result

    # 5. Fallback: take whatever is left up to the first non-letter
    m = re.match(r"^([A-Z]+)", rest)
    if m:
        result["product_name"] = m.group(1)
        return result

    return None


# Fallback for files like JPSS2_VIIRS.20260831.L3m.DAY.CHL_chlor_a.4km.nc
_NOAA_PATTERN = re.compile(
    r"^JPSS\d+_VIIRS\."
    r"(?P<date>\d{8})"          # YYYYMMDD
    r"\."
    r"L(?P<level>\dm?)"
    r"\."
    r"(?P<rest>.+?)"
    r"\.(?P<ext>nc|h5)$",
    re.IGNORECASE,
)

# Hyphenated older format: O2-SCT-AWV50.nc
_HYPHEN_PATTERN = re.compile(
    r"^(?P<sat>O\d+|E\d+)[\-_](?P<inst>\w+)[\-_](?P<product>\w+)\.(?P<ext>nc|h5)$",
    re.IGNORECASE,
)


@dataclass
class ParsedFile:
    """The result of parsing one satellite data file."""

    path: Path
    file_type: str                # "NetCDF4" / "HDF5" / "unknown"
    satellite: str | None = None
    instrument: str | None = None
    processing_level: str | None = None
    product_name: str | None = None
    date: datetime | None = None
    resolution_km: float | None = None
    version: str | None = None

    # Variable / dimension info extracted from the file
    variables: dict[str, dict] = field(default_factory=dict)
    # Each entry: {name: {dtype, dims, shape, units, long_name, attrs}}

    coordinates: dict[str, Any] = field(default_factory=dict)
    # 'lat': ndarray, 'lon': ndarray, 'time': list[str], etc.

    file_attrs: dict[str, Any] = field(default_factory=dict)
    # File-level attributes (institution, source, history, etc.)

    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line human-readable summary."""
        parts = [self.path.name]
        if self.satellite and self.product_name:
            parts.append(f"({self.satellite} {self.product_name})")
        if self.date:
            parts.append(f"date={self.date.date()}")
        if self.resolution_km:
            parts.append(f"{self.resolution_km}km grid")
        if self.variables:
            n = len(self.variables)
            sample = ", ".join(list(self.variables)[:4])
            parts.append(f"{n} vars: {sample}{'…' if n > 4 else ''}")
        return "  ·  ".join(parts)


# ---------------------------------------------------------------------------
# Filename parsing (no file I/O needed)


def parse_filename(name: str) -> dict:
    """Extract metadata from a MOSDAC-style filename.

    Returns a dict with whatever could be parsed. Missing fields are None.
    Always succeeds — never raises.
    """
    result = {
        "satellite": None,
        "instrument": None,
        "processing_level": None,
        "product_name": None,
        "date": None,
        "resolution_km": None,
        "version": None,
    }

    # Try MOSDAC block pattern first
    block = _parse_mosdac_block(name)
    if block:
        result.update(block)

    # Now extract the rest of the filename (date, res, version)
    # by stripping the leading block we just parsed.
    upper = name.upper()
    head_end = 0
    if block and block.get("satellite"):
        head_end += len(block["satellite"])
    if block and block.get("instrument"):
        head_end += len(block["instrument"])
    if block and block.get("processing_level"):
        head_end += len(block["processing_level"])
    if block and block.get("product_name"):
        head_end += len(block["product_name"])
    tail = upper[head_end:]

    # Date is the first run of 6-7 digits in the tail
    m = re.search(r"(\d{6,7})", tail)
    if m:
        result["date"] = _parse_date_str(m.group(1))

    # Resolution: e.g. "25km", "4k", "12.5km"
    # Match "Nkm" or "Nk" only when followed by separator (_ or . or end)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(km|k)(?=[._]|$)", tail, re.IGNORECASE)
    if m:
        try:
            result["resolution_km"] = float(m.group(1))
        except ValueError:
            pass

    # Version: e.g. "v1.0.5"
    m = re.search(r"(v\d+(?:\.\d+){0,3})", tail, re.IGNORECASE)
    if m:
        result["version"] = m.group(1).lower()

    # NOAA VIIRS pattern (if not matched as MOSDAC)
    if not result["satellite"]:
        m = _NOAA_PATTERN.match(name)
        if m:
            result["satellite"] = "JPSS"
            result["instrument"] = "VIIRS"
            result["processing_level"] = "L" + m.group("level")
            result["date"] = _parse_date_str(m.group("date"))
            rest = m.group("rest")
            rm = re.search(r"(\d+(?:\.\d+)?)km", rest, re.IGNORECASE)
            if rm:
                try:
                    result["resolution_km"] = float(rm.group(1))
                except ValueError:
                    pass

    # Hyphenated older format
    if not result["satellite"]:
        m = _HYPHEN_PATTERN.match(name)
        if m:
            result["satellite"] = m.group("sat").upper()
            result["instrument"] = m.group("inst").upper()
            result["product_name"] = m.group("product").upper()

    return result


def _parse_date_str(s: str | None) -> datetime | None:
    if not s:
        return None
    if len(s) == 7:  # YYYYDDD (Julian day)
        try:
            year = int(s[:4])
            doy = int(s[4:])
            return datetime(year, 1, 1) + timedelta(days=doy - 1)
        except (ValueError, OverflowError):
            return None
    if len(s) == 8:  # YYYYMMDD
        try:
            return datetime.strptime(s, "%Y%m%d")
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# File parsing (uses xarray if available, falls back gracefully)


def _ensure_stack():
    """Import xarray + h5py lazily, with a friendly error if missing."""
    try:
        import xarray  # noqa: F401
        import h5py  # noqa: F401
        return True
    except ImportError as e:
        raise ImportError(
            "NetCDF/HDF5 parsing needs the scientific stack. "
            "Install with:  pip install xarray netCDF4 h5py"
        ) from e


def detect_file_type(path: Path) -> str:
    """Return 'NetCDF4', 'NetCDF3', 'HDF5', or 'unknown' based on magic bytes."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return "unknown"
    # NetCDF-4 / HDF5: b'\\x89HDF\\r\\n\\x1a\\n'
    if head.startswith(b"\x89HDF\r\n\x1a\n"):
        if path.suffix.lower() in (".h5", ".hdf5", ".he5"):
            return "HDF5"
        return "NetCDF4"
    # NetCDF-3 classic: b'CDF\\x01' or b'CDF\\x02'
    if head[:3] == b"CDF" and head[3:4] in (b"\x01", b"\x02"):
        return "NetCDF3"
    return "unknown"


def parse(path: str | Path) -> ParsedFile:
    """Parse a NetCDF4 or HDF5 file. Returns a ParsedFile with all the metadata.

    Never raises on malformed files — instead, fills `warnings` and returns
    a partial result.
    """
    p = Path(path)
    pf = ParsedFile(path=p, file_type=detect_file_type(p))

    # Step 1: parse the filename (free, no I/O)
    name_meta = parse_filename(p.name)
    pf.satellite = name_meta["satellite"]
    pf.instrument = name_meta["instrument"]
    pf.processing_level = name_meta["processing_level"]
    pf.product_name = name_meta["product_name"]
    pf.date = name_meta["date"]
    pf.resolution_km = name_meta["resolution_km"]
    pf.version = name_meta["version"]

    # Step 2: open the file
    try:
        _ensure_stack()
        import xarray as xr

        # xarray auto-detects engine from extension, but we want to
        # be explicit so NetCDF-3 files don't get mis-handled.
        if pf.file_type == "NetCDF4":
            engine = "netcdf4"
        elif pf.file_type == "NetCDF3":
            # NetCDF-3 classic - use the netcdf4 engine which can
            # read both classic (CDF1) and 64-bit offset (CDF2) formats
            engine = "netcdf4"
        elif pf.file_type == "HDF5":
            engine = "h5netcdf"
        else:
            pf.warnings.append(f"Unknown file type: {pf.file_type}")
            return pf

        with xr.open_dataset(p, engine=engine) as ds:
            # File-level attributes
            pf.file_attrs = {k: str(v) for k, v in ds.attrs.items()}

            # Variables
            for name, var in ds.data_vars.items():
                info = {
                    "dtype": str(var.dtype),
                    "dims": list(var.dims),
                    "shape": list(var.shape),
                }
                if "units" in var.attrs:
                    info["units"] = str(var.attrs["units"])
                if "long_name" in var.attrs:
                    info["long_name"] = str(var.attrs["long_name"])
                # Stash a small sample for inspection (capped to avoid memory blowup)
                try:
                    arr = var.values
                    if arr.size <= 10:
                        info["sample"] = arr.tolist()
                    else:
                        flat = arr.ravel()
                        finite = flat[~_is_masked_or_nan(flat)]
                        if finite.size:
                            info["sample"] = {
                                "min": float(finite.min()),
                                "max": float(finite.max()),
                                "mean": float(finite.mean()),
                            }
                except Exception:  # noqa: BLE001
                    pass
                pf.variables[name] = info

            # Coordinates
            for name in ("lat", "latitude", "Latitude", "lon", "longitude",
                         "Longitude", "time", "Time"):
                if name in ds.coords:
                    arr = ds[name].values
                    if name in ("lat", "latitude", "Latitude"):
                        pf.coordinates["lat"] = arr
                    elif name in ("lon", "longitude", "Longitude"):
                        pf.coordinates["lon"] = arr
                    elif name in ("time", "Time"):
                        try:
                            pf.coordinates["time"] = [
                                str(t) for t in arr
                            ]
                        except Exception:  # noqa: BLE001
                            pf.coordinates["time"] = []

    except ImportError:
        pf.warnings.append(
            "Scientific stack (xarray/netCDF4/h5py) not installed. "
            "Only filename metadata was extracted."
        )
    except Exception as exc:  # noqa: BLE001
        pf.warnings.append(f"Could not fully parse file: {exc!s}")

    return pf


def _is_masked_or_nan(arr):
    """Helper to filter out masked/nan values when computing sample stats."""
    try:
        import numpy as np
        if np.ma.is_masked(arr):
            return np.ma.getmaskarray(arr)
        return np.isnan(arr)
    except Exception:  # noqa: BLE001
        return [False] * len(arr)


# ---------------------------------------------------------------------------
# Domain-specific extractors — these turn a ParsedFile into something
# the ORCA agents can use directly.

def extract_at_location(pf: ParsedFile, lat: float, lon: float,
                        variable: str | None = None,
                        max_dist_deg: float = 2.0) -> dict | None:
    """Find the value of a variable nearest to (lat, lon).

    Returns a dict like:
        {
            "variable": "chlor_a",
            "value": 0.45,
            "units": "mg m^-3",
            "lat": 19.0,
            "lon": 73.0,
            "distance_deg": 0.12,
            "source": "E06SCTL4UI_...",
        }
    or None if the file has no usable data near the requested point.
    """
    if not pf.coordinates.get("lat") or not pf.coordinates.get("lon"):
        return None

    lats = pf.coordinates["lat"]
    lons = pf.coordinates["lon"]

    # Find nearest grid cell
    try:
        import numpy as np
        lat_idx = int(np.argmin(np.abs(lats - lat)))
        lon_idx = int(np.argmin(np.abs(lons - lon)))
    except Exception:  # noqa: BLE001
        return None

    found_lat = float(lats[lat_idx])
    found_lon = float(lons[lon_idx])
    dist = ((found_lat - lat) ** 2 + (found_lon - lon) ** 2) ** 0.5
    if dist > max_dist_deg:
        return None

    # Pick the variable to extract
    candidates = []
    if variable:
        candidates = [variable]
    else:
        # Heuristic: look for known chlorophyll / wind / SST names
        all_names = list(pf.variables)
        chlorophyll_keys = ("chlor", "chl", "oc4", "ocx")
        wind_keys = ("wind", "u_wind", "v_wind", "wspd", "wdir", "u10", "v10")
        upwelling_keys = ("upwelling", "ui", "ekman", "pumping")
        for keys in (chlorophyll_keys, wind_keys, upwelling_keys):
            for name in all_names:
                if any(k in name.lower() for k in keys):
                    candidates.append(name)
                    break
        if not candidates and all_names:
            candidates = all_names[:1]

    if not candidates:
        return None

    chosen = candidates[0]
    var_info = pf.variables[chosen]
    sample = var_info.get("sample")
    # We need the actual value at (lat_idx, lon_idx). Re-open the file
    # since xarray closed it after parse() returned.
    try:
        import xarray as xr
        # NetCDF3, NetCDF4, HDF5 all use the netcdf4 engine
        if pf.file_type in ("NetCDF3", "NetCDF4", "HDF5"):
            engine = "netcdf4"
        else:
            engine = "scipy"  # generic fallback
        with xr.open_dataset(pf.path, engine=engine) as ds:
            arr = ds[chosen].values
            # Take the value at the nearest indices
            if arr.ndim == 2:
                value = float(arr[lat_idx, lon_idx])
            elif arr.ndim == 3:
                # 3D = (time, lat, lon) — use first timestep
                value = float(arr[0, lat_idx, lon_idx])
            else:
                value = None
    except Exception:  # noqa: BLE001
        value = sample.get("mean") if isinstance(sample, dict) else None

    return {
        "variable": chosen,
        "value": value,
        "units": var_info.get("units"),
        "long_name": var_info.get("long_name"),
        "lat": found_lat,
        "lon": found_lon,
        "distance_deg": float(dist),
        "source": pf.path.name,
    }
