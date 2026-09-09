"""Debug helper: dump the EXACT shape of Open-Meteo's multi-point response.

Run: python dump_openmeteo_shape.py
Paste the output back to chat.
"""
import sys as _sys, pathlib as _pathlib  # tools/ se bhi repo-root imports kaam karein
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

import json
import sys
import urllib.parse
import urllib.request

URL = "https://marine-api.open-meteo.com/v1/marine?" + urllib.parse.urlencode({
    "latitude": "18.0,18.5",
    "longitude": "72.0,72.5",
    "daily": "sea_surface_temperature_max,sea_surface_temperature_min,wave_height_max",
    "start_date": "2026-08-01",
    "end_date": "2026-08-03",
    "timezone": "auto",
})

print("=" * 70)
print("URL:", URL)
print("=" * 70)

req = urllib.request.Request(URL, headers={"User-Agent": "ORCA/1.0"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        print("RAW BYTES (first 500):", raw[:500])
        print("RAW BYTES (last 200):", raw[-200:])
        print("=" * 70)
        text = raw.decode("utf-8", errors="replace")
        data = json.loads(text)
except Exception as e:
    print("ERROR:", type(e).__name__, e)
    sys.exit(1)

print("TOP TYPE:", type(data).__name__)
print("=" * 70)

if isinstance(data, dict):
    print("TOP KEYS:", list(data.keys()))
    for k, v in data.items():
        t = type(v).__name__
        if isinstance(v, list):
            sample = v[:3]
            print(f"  {k}: list(len={len(v)}) sample={sample}")
        elif isinstance(v, dict):
            print(f"  {k}: dict(keys={list(v.keys())})")
            for k2, v2 in v.items():
                t2 = type(v2).__name__
                if isinstance(v2, list):
                    print(f"    .{k2}: list(len={len(v2)}) sample={v2[:3]}")
                else:
                    print(f"    .{k2}: {t2} = {repr(v2)[:100]}")
        else:
            print(f"  {k}: {t} = {repr(v)[:200]}")
elif isinstance(data, list):
    print("LIST LEN:", len(data))
    for i, item in enumerate(data[:3]):
        print(f"  [{i}] type={type(item).__name__}")
        if isinstance(item, dict):
            print(f"      keys={list(item.keys())}")
            for k, v in item.items():
                if isinstance(v, list):
                    print(f"        {k}: list(len={len(v)}) sample={v[:3]}")
                else:
                    print(f"        {k}: {type(v).__name__} = {repr(v)[:200]}")
        else:
            print(f"      value={repr(item)[:200]}")
else:
    print("VALUE:", repr(data)[:500])
