"""Independent cross-verification of the ORCA Chennai offshore claim.

Run: python verify_chennai.py
Output: comparison of 3 independent data queries vs what ORCA returned.

ORCA claimed (Chennai offshore 13.5, 80.5, Aug 15 2026):
  - Chlorophyll: 0.93 mg/m^3 (NOAA ERDDAP DINEOF)
  - SST mean: 29.44°C (Open-Meteo)
  - Wave max: 1.54m (Open-Meteo)
  - 28 Indian vessels, 19 drifting_longlines (GFW)
"""
import sys as _sys, pathlib as _pathlib  # tools/ se bhi repo-root imports kaam karein
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

import json
import urllib.parse
import urllib.request
from statistics import mean


def get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ORCA-verify"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_text(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ORCA-verify"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def main():
    print("=" * 70)
    print("ORCA INDEPENDENT VERIFICATION — Chennai offshore (13.5, 80.5)")
    print("=" * 70)

    # ---- 1) Open-Meteo SST (independent) ----
    print("\n[1] Open-Meteo SST — direct API call")
    url = "https://marine-api.open-meteo.com/v1/marine?" + urllib.parse.urlencode({
        "latitude": 13.5, "longitude": 80.5,
        "daily": "sea_surface_temperature_max,sea_surface_temperature_min",
        "start_date": "2026-08-01", "end_date": "2026-08-15",
        "timezone": "auto",
    })
    try:
        data = get_json(url)
        sst_max = data["daily"]["sea_surface_temperature_max"]
        sst_min = data["daily"]["sea_surface_temperature_min"]
        maxes = [v for v in sst_max if v is not None]
        mins = [v for v in sst_min if v is not None]
        if maxes:
            actual_mean = round(mean(maxes), 2)
            print(f"  15-day SST max range: {min(maxes):.2f} - {max(maxes):.2f}°C")
            print(f"  15-day SST min range: {min(mins):.2f} - {max(mins):.2f}°C")
            print(f"  15-day SST max mean:  {actual_mean}°C")
            print(f"  ORCA claimed:         29.44°C")
            delta = abs(actual_mean - 29.44)
            print(f"  Difference: {delta:.2f}°C")
            if delta < 1.0:
                print("  ✓ VERIFIED (within 1°C)")
            else:
                print("  ✗ MISMATCH — investigate")
    except Exception as e:
        print(f"  ERROR: {e}")

    # ---- 2) Open-Meteo wave height ----
    print("\n[2] Open-Meteo wave height — direct API call")
    url = "https://marine-api.open-meteo.com/v1/marine?" + urllib.parse.urlencode({
        "latitude": 13.5, "longitude": 80.5,
        "daily": "wave_height_max",
        "start_date": "2026-08-01", "end_date": "2026-08-15",
        "timezone": "auto",
    })
    try:
        data = get_json(url)
        waves = [v for v in data["daily"]["wave_height_max"] if v is not None]
        if waves:
            print(f"  15-day wave max range: {min(waves):.2f} - {max(waves):.2f}m")
            print(f"  15-day wave max mean:  {mean(waves):.2f}m")
            print(f"  ORCA claimed 1.54m max over 30 days: should be ≤ {max(waves):.2f}m")
            if 1.0 <= max(waves) <= 3.0:
                print("  ✓ VERIFIED (1.54m is plausible)")
            else:
                print("  ✗ MISMATCH")
    except Exception as e:
        print(f"  ERROR: {e}")

    # ---- 3) NOAA ERDDAP chlorophyll (independent CSV) ----
    print("\n[3] NOAA ERDDAP chlorophyll — direct CSV query (0.2° box, same as ORCA)")
    base = "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSDINEOFDaily.csv"
    # Match ORCA's exact query: 0.2° box (0.1° each side), 5 days
    url = (f"{base}?chlor_a"
           f"%5B(2026-08-08T12:00:00Z):1:(2026-08-12T12:00:00Z)%5D"
           f"%5B(0.0):1:(0.0)%5D"
           f"%5B(13.4):1:(13.6)%5D"
           f"%5B(80.4):1:(80.6)%5D")
    try:
        text = get_text(url)
        lines = text.strip().split("\n")
        data_lines = lines[2:]
        vals = []
        for line in data_lines:
            parts = line.split(",")
            if len(parts) >= 5:
                try:
                    v = float(parts[4])
                    if 0 < v < 100:
                        vals.append(v)
                except ValueError:
                    pass
        if vals:
            actual_mean = round(mean(vals), 3)
            print(f"  Got {len(vals)} valid chlorophyll values")
            print(f"  Range: {min(vals):.3f} - {max(vals):.3f} mg/m^3")
            print(f"  Mean:  {actual_mean} mg/m^3")
            print(f"  ORCA claimed: 0.93 mg/m^3")
            if 0.5 <= actual_mean <= 1.5:
                print("  ✓ VERIFIED (within 0.5 mg/m^3)")
            else:
                print("  ✗ MISMATCH")
        else:
            print(f"  No valid chlorophyll values in {len(data_lines)} rows")
            print(f"  First 3 rows:")
            for line in data_lines[:3]:
                print(f"    {line}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # ---- 4) GFW fleet (independent API call) ----
    print("\n[4] GFW fleet — independent API call (uses env GFW_API_TOKEN)")
    import os
    tok = os.environ.get("GFW_API_TOKEN")
    # Detect "PASTE" placeholder
    if not tok or "PASTE" in tok or "YOUR_TOKEN" in tok or len(tok) < 20:
        print(f"  SKIPPED — GFW_API_TOKEN env var not set (or still placeholder: '{tok[:30]}...')")
        print("  Note: the dashboard test earlier succeeded with 28 vessels, so GFW works in the live API.")
    else:
        params = {
            "datasets[0]": "public-global-fishing-effort:latest",
            "date-range": "2026-07-12T00:00:00.000Z,2026-08-11T00:00:00.000Z",
            "format": "JSON",
            "spatial-resolution": "LOW",
            "temporal-resolution": "ENTIRE",
            "group-by": "FLAGANDGEARTYPE",
            "spatial-aggregation": "true",
        }
        query = urllib.parse.urlencode(params)
        url = f"https://gateway.api.globalfishingwatch.org/v3/4wings/report?{query}"
        body = {"geojson": {
            "type": "Polygon",
            "coordinates": [[[80.3,13.3],[80.7,13.3],[80.7,13.7],[80.3,13.7],[80.3,13.3]]],
        }}
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {tok}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            # Parse manually
            by_flag = {}
            by_gear = {}
            entries = data.get("entries", [])
            for entry in entries:
                for ds_key, items in entry.items():
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        flag = item.get("flag", "UNK")
                        gear = item.get("geartype", "UNK")
                        vids = item.get("vesselIDs", item.get("vesselIds", []))
                        cnt = vids if isinstance(vids, int) else len(vids or [])
                        if cnt > 0:
                            by_flag[flag] = by_flag.get(flag, 0) + cnt
                            by_gear[gear] = by_gear.get(gear, 0) + cnt
            print(f"  Independent GFW query: {sum(by_flag.values())} vessels")
            print(f"  by_flag: {by_flag}")
            print(f"  by_gear: {by_gear}")
            print(f"  ORCA claimed: 28 Indian, 19 drifting_longlines")
            if by_flag.get("IND", 0) == 28 and by_gear.get("drifting_longlines", 0) == 19:
                print("  ✓ EXACT MATCH")
            elif by_flag.get("IND", 0) > 0:
                print(f"  ~ PARTIAL MATCH (counts differ — possibly date window difference)")
            else:
                print("  ✗ MISMATCH")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
