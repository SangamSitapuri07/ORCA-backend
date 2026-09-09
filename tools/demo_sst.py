"""Quick demo: print SST for 8 Indian coastal points."""
import sys as _sys, pathlib as _pathlib  # tools/ se bhi repo-root imports kaam karein
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

from pipeline.openmeteo_sst import demo_indian_ocean_sst

results = demo_indian_ocean_sst("2026-08-01", "2026-08-30")
for r in results:
    name = r.get("name", "?")
    sst_min = r.get("sst_min", "?")
    sst_max = r.get("sst_max", "?")
    wave_max = r.get("wave_max", "?")
    err = r.get("error", "")
    if err:
        print(f"{name:30s}  ERROR: {err}")
    else:
        print(f"{name:30s}  SST {sst_min}->{sst_max}°C  wave max {wave_max}m")
