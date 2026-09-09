"""Live demo: full ORCA pipeline with 4+ data sources + 10 agents.

This is the SIH pitch demo. Run with your GFW_API_TOKEN set:

  $env:GFW_API_TOKEN = "your_token"
  python demo_orca_reasoner.py
"""
import sys as _sys, pathlib as _pathlib  # tools/ se bhi repo-root imports kaam karein
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

import json
import os

from pipeline.orca_data import zone_snapshot
from pipeline.reasoner import reason


def main():
    if not os.environ.get("GFW_API_TOKEN"):
        print("⚠️  GFW_API_TOKEN not set — GFW calls will be skipped (mocked).")

    print("=" * 70)
    print("ORCA Marine Intelligence — full pipeline demo")
    print("=" * 70)

    # Mumbai offshore, Aug 15 2026
    snap = zone_snapshot(19.0, 72.8, "2026-08-15", include_gfw=True)
    print("\n[ZoneSnapshot]")
    print(json.dumps({k: v for k, v in snap.items()
                      if k not in ("data_sources_failed", "daily")},
                     indent=2, default=str))
    if snap.get("data_sources_failed"):
        print("\n[Failed sources]")
        for f in snap["data_sources_failed"]:
            print(f"  - {f}")

    print("\n" + "=" * 70)
    print("[Multi-Agent Reasoning]")
    print("=" * 70)
    insight = reason(snap)
    print(f"\nOverall risk: {insight['overall_risk'].upper()}")
    print(f"\nSummary: {insight['summary']}")
    print(f"\nRecommendation: {insight['recommendation']}")
    print("\n[Per-agent results]")
    for a in insight["agents"]:
        print(f"\n  [{a['agent']}] risk={a['risk_level']}")
        print(f"    {a['summary']}")
        for f in a.get("findings", [])[:5]:
            print(f"    - {f['severity']:5s} {f['type']:30s} {f['msg']}")


if __name__ == "__main__":
    main()
