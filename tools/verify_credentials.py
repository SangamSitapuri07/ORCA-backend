"""
Verify your .env file has working credentials for BOTH services.

This script does NOT print or send your password/token anywhere.
It only reads them from the .env file and uses them to call
the real APIs to prove they work.

Run on YOUR machine (not sandbox):
    cd $HOME\\Desktop\\orca-setup\\SIH
    python verify_credentials.py
"""
import sys as _sys, pathlib as _pathlib  # tools/ se bhi repo-root imports kaam karein
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

import os
import sys
import urllib.error
from pathlib import Path


def load_dotenv(path: str = ".env") -> dict[str, str]:
    """Read a .env file (KEY=value per line) into a dict."""
    env = {}
    p = Path(path)
    if not p.exists():
        print(f"⚠️  {path} not found in {os.getcwd()}")
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    print("=" * 70)
    print("  ORCA — verify your credentials are set up correctly")
    print("=" * 70)
    print()

    env = load_dotenv()
    # Also pick up anything from the OS environment (in case .env was
    # already loaded into the shell).
    for k in ("MOSDAC_USERNAME", "MOSDAC_PASSWORD", "GFW_API_TOKEN"):
        if k not in env and k in os.environ:
            env[k] = os.environ[k]

    # ──── GFW ────
    print("─" * 70)
    print("1) GFW API token (Global Fishing Watch)")
    print("─" * 70)
    gfw_token = env.get("GFW_API_TOKEN", "")
    if not gfw_token:
        print("  ❌ GFW_API_TOKEN is NOT set in .env")
        print("     Add this line to .env (paste your real token):")
        print("         GFW_API_TOKEN=eyJhbGc...your_full_token...")
    else:
        print(f"  ✓ GFW_API_TOKEN is set ({len(gfw_token)} chars)")
        if gfw_token.startswith("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6"):
            print("  ⚠️  This looks like a PUBLIC KEY, not an access token.")
            print("     It won't work for the 4wings API. Get the access token")
            print("     from https://globalfishingwatch.org/our-apis/tokens/")
            print("     (click the eye icon 👁 next to orca-pipeline token)")
        elif gfw_token.count(".") == 2 and gfw_token.startswith("eyJ"):
            print("  ✓ Format looks like a JWT access token")
        else:
            print("  ⚠️  Format doesn't look like a JWT. Double-check you copied")

        # Now actually call GFW to prove the token works
        print()
        print("  Testing GFW API call for Indian EEZ (region-id 8480)...")
        try:
            import json
            import urllib.request
            url = (
                "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
                "?datasets%5B0%5D=public-global-fishing-effort%3Alatest"
                "&date-range=2026-08-03%2C2026-09-02"
                "&format=JSON"
                "&spatial-resolution=LOW"
                "&temporal-resolution=ENTIRE"
                "&group-by=VESSEL_ID"
                "&spatial-aggregation=true"
            )
            # v3 official: plain-date date-range in URL + EEZ region-id in body (docs-verified)
            body = {"region": {"dataset": "public-eez-areas", "id": 8480}}
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {gfw_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "ORCA/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            total = data.get("total", "?")
            n_entries = len(data.get("entries", []))
            print(f"  ✅ GFW API call succeeded!")
            print(f"     Total fishing hours: {total}")
            print(f"     Number of entries: {n_entries}")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")[:300]
            print(f"  ❌ GFW returned HTTP {e.code}: {e.reason}")
            print(f"     Details: {body_text}")
            if e.code == 401:
                print("     → Your token is wrong or expired. Get a new one")
                print("       from https://globalfishingwatch.org/our-apis/tokens/")
            elif e.code == 403:
                print("     → Token doesn't have access to the 4wings endpoint.")
                print("       Make sure you applied for 'API access' (not just registered)")
        except Exception as e:
            print(f"  ❌ GFW call failed: {type(e).__name__}: {e}")

    # ──── MOSDAC ────
    print()
    print("─" * 70)
    print("2) MOSDAC credentials (Indian 🇮🇳 satellite data)")
    print("─" * 70)
    user = env.get("MOSDAC_USERNAME", "")
    pwd = env.get("MOSDAC_PASSWORD", "")
    if not user or not pwd:
        print("  ❌ MOSDAC_USERNAME or MOSDAC_PASSWORD is NOT set in .env")
        print("     Add these two lines to .env (paste your real values):")
        print("         MOSDAC_USERNAME=your.email@example.com")
        print("         MOSDAC_PASSWORD=your_mosdac_password")
    else:
        print(f"  ✓ MOSDAC_USERNAME = {user}")
        print(f"  ✓ MOSDAC_PASSWORD = ({len(pwd)} chars, hidden)")

        # Try the actual login
        print()
        print("  Testing MOSDAC login...")
        try:
            # Add the project root to sys.path so 'pipeline' imports
            project_root = str(Path(__file__).parent.resolve())
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from pipeline.mosdac_auth import quick_check
            ok = quick_check()
            if ok:
                print("  ✅ MOSDAC login works!")
            else:
                print("  ❌ MOSDAC login failed — see error above")
        except ImportError:
            print("  ⚠️  Could not import pipeline.mosdac_auth.")
            print("     Run this from the project root: cd $HOME\\Desktop\\orca-setup\\SIH")
        except Exception as e:
            print(f"  ❌ MOSDAC test failed: {type(e).__name__}: {e}")

    # ──── Summary ────
    print()
    print("=" * 70)
    print("  Summary")
    print("=" * 70)
    gfw_ok = bool(gfw_token) and not gfw_token.startswith("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6")
    mosdac_ok = bool(user) and bool(pwd)
    if gfw_ok and mosdac_ok:
        print("  ✅ Both credentials are set. Restart your FastAPI backend to apply.")
        print()
        print("     Terminal 1:")
        print("         Ctrl+C   (to stop the old uvicorn)")
        print("         python -m uvicorn backend.main:app --reload --port 8000")
        print()
        print("     Then in the browser:")
        print("         http://localhost:3000  →  click Chennai")
        print("         You should see 'Global Fishing Watch (effort + fleet)'")
        print("         in the 'Data sources used' list (no longer Failed).")
    else:
        print("  ⚠️  Some credentials are missing. Fix them above and re-run.")
    print()


if __name__ == "__main__":
    main()
