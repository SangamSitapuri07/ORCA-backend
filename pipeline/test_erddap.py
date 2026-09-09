"""`python -m pipeline.test_erddap` — verify the NOAA ERDDAP DINEOF chlorophyll.

Updated for the correct dataset ID: noaacwNPPN20VIIRSDINEOFDaily
Variable: chlor_a (not chl_oci)

Tries several URL formats to find the one that works:
- .csv with explicit date
- .csv with [last]
- .json (simpler format)
- specific formats
"""
from __future__ import annotations

import urllib.request
from datetime import datetime, timedelta


ERDDAP_BASE = "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSDINEOFDaily"


def main():
    lat, lon = 19.0, 72.8
    print("Testing NOAA ERDDAP DINEOF chlorophyll for Mumbai (19.0, 72.8)")
    print()
    print("Dataset: noaacwNPPN20VIIRSDINEOFDaily")
    print("Variable: chlor_a (DINEOF Gap-Filled)")
    print()

    # Try a series of formats to find what works
    attempts = [
        ("specific date with full axis order",
         f"{ERDDAP_BASE}.csv?chlor_a[(2026-08-30T12:00:00Z):1:(2026-08-30T12:00:00Z)][(0.0):1:(0.0)][({lat-0.1:.4f}):1:({lat+0.1:.4f})][({lon-0.1:.4f}):1:({lon+0.1:.4f})]"),
        ("[last] with full axis order",
         f"{ERDDAP_BASE}.csv?chlor_a[last][(0.0):1:(0.0)][({lat-0.1:.4f}):1:({lat+0.1:.4f})][({lon-0.1:.4f}):1:({lon+0.1:.4f})]"),
        ("[last] JSON format",
         f"{ERDDAP_BASE}.json?chlor_a[last][(0.0):1:(0.0)][({lat-0.1:.4f}):1:({lat+0.1:.4f})][({lon-0.1:.4f}):1:({lon+0.1:.4f})]"),
        ("[last] no altitude (skip middle dim)",
         f"{ERDDAP_BASE}.csv?chlor_a[last][({lat-0.1:.4f}):1:({lat+0.1:.4f})][({lon-0.1:.4f}):1:({lon+0.1:.4f})]"),
    ]

    for label, url in attempts:
        print(f"Trying {label}...")
        print(f"URL: {url[:200]}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
                print(f"✅ Got {len(text)} bytes!")
                print()
                print(text[:500])
                print()
                print("=" * 60)
                print()
        except urllib.error.HTTPError as e:
            print(f"❌ HTTP {e.code}: {e.reason}")
            try:
                err_body = e.read().decode("utf-8")
                print(f"   Body: {err_body[:300]}")
            except Exception:
                pass
            print()
        except Exception as e:
            print(f"❌ Error: {type(e).__name__}: {e}")
            print()


if __name__ == "__main__":
    main()
