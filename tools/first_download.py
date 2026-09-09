"""First real MOSDAC granule download (proof-of-life).

Run from repo root:  python first_download.py
Grabs 1 EOS-06 OCM ocean-colour (chlorophyll-a) granule for the Gujarat box.
"""
import sys as _sys, pathlib as _pathlib  # tools/ se bhi repo-root imports kaam karein
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

from pipeline import mosdac_auth as M

s = M.login()
print("token OK")

d = M.search("E06OCM_L2C_LAC_OC", start="2026-08-31", end="2026-08-31",
             bbox="66.0,18.0,72.5,23.5", count="5")
entries = d.get("entries", [])
print(f"{d.get('totalResults')} files us din Gujarat box me")
if not entries:
    raise SystemExit("koi granule nahi mila — kabhi aur try karna")

rid = entries[0]["id"]
print("downloading granule id:", rid, "…")
path = M.download_file(s, rid, out_dir=r"C:\Users\sanga\Desktop\ORCA_DATA\mosdac")
print("SAVED ✅", path)
