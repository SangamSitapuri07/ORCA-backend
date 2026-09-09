"""`python -m pipeline.test_incois_live` — verify the INCOIS OPeNDAP connection.

Reads the live INCOIS OCM-2 chlorophyll file at our test point
(Mumbai, 19.0, 72.8) and prints what it finds.

If the network is reachable, prints a real chlorophyll value.
If not, prints the error.
"""
from __future__ import annotations

from pipeline.incois import get_chlorophyll


def main():
    print("Testing INCOIS OCM-2 chlorophyll via OPeNDAP...")
    print()
    result = get_chlorophyll(19.0, 72.8, "2020-05-01")
    if result is None:
        print("❌ No data (likely out of region or date)")
        return
    if "error" in result:
        print(f"❌ Error: {result['error']}")
        if "source" in result:
            print(f"   Source: {result['source']}")
        return
    print("✅ Got real INCOIS chlorophyll data!")
    print()
    for k, v in result.items():
        print(f"   {k:>14}: {v}")


if __name__ == "__main__":
    main()
