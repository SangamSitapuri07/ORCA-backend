"""
Verify your .env file has working credentials for BOTH services.

This script never prints your password or token. It reads backend environment
configuration (and optional local .env), then sends credentials only to the
configured GFW/MOSDAC authentication endpoints for measured checks.

Run from the ORCA-backend project root:
    python tools/verify_credentials.py
"""
import sys as _sys, pathlib as _pathlib  # tools/ se bhi repo-root imports kaam karein
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parents[1]))

import os
import urllib.error
from datetime import date, timedelta
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
    gfw_live_ok = False
    if not gfw_token:
        print("  ❌ GFW_API_TOKEN is not configured in the environment or .env")
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
            end_date = date.today() - timedelta(days=4)
            start_date = end_date - timedelta(days=29)
            date_range = f"{start_date.isoformat()}%2C{end_date.isoformat()}"
            url = (
                "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
                "?datasets%5B0%5D=public-global-fishing-effort%3Alatest"
                f"&date-range={date_range}"
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
            from pipeline.gfw import _parse_effort_report
            hours, vessel_ids, entries = _parse_effort_report(data)
            gfw_live_ok = True
            print("  ✅ GFW API call succeeded!")
            print(f"     Measured fishing hours in entries: {hours}")
            print(f"     Unique vessel IDs: {len(vessel_ids)}")
            print(f"     Top-level result groups: {data.get('total', '?')}")
            print(f"     Top-level entries: {len(entries)}")
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
    mosdac_live_ok = False
    if not user or not pwd:
        print("  ❌ MOSDAC_USERNAME or MOSDAC_PASSWORD is not configured in the environment or .env")
        print("     Add these two lines to .env (paste your real values):")
        print("         MOSDAC_USERNAME=your.email@example.com")
        print("         MOSDAC_PASSWORD=your_mosdac_password")
    else:
        print("  ✓ MOSDAC_USERNAME is set (value hidden)")
        print(f"  ✓ MOSDAC_PASSWORD is set ({len(pwd)} chars, hidden)")

        # Try the actual login
        print()
        print("  Testing MOSDAC login...")
        previous_user = os.environ.get("MOSDAC_USERNAME")
        previous_password = os.environ.get("MOSDAC_PASSWORD")
        os.environ["MOSDAC_USERNAME"] = user
        os.environ["MOSDAC_PASSWORD"] = pwd
        try:
            from pipeline.mosdac_auth import quick_check
            ok = quick_check()
            if ok:
                mosdac_live_ok = True
                print("  ✅ MOSDAC login works!")
            else:
                print("  ❌ MOSDAC login failed — see error above")
        except ImportError:
            print("  ⚠️  Could not import pipeline.mosdac_auth.")
            print("     Run this command from the ORCA-backend project root.")
        except Exception as e:
            print(f"  ❌ MOSDAC test failed: {type(e).__name__}: {e}")
        finally:
            if previous_user is None:
                os.environ.pop("MOSDAC_USERNAME", None)
            else:
                os.environ["MOSDAC_USERNAME"] = previous_user
            if previous_password is None:
                os.environ.pop("MOSDAC_PASSWORD", None)
            else:
                os.environ["MOSDAC_PASSWORD"] = previous_password

    # ──── Summary ────
    print()
    print("=" * 70)
    print("  Summary")
    print("=" * 70)
    all_checks_passed = gfw_live_ok and mosdac_live_ok
    if all_checks_passed:
        print("  ✅ Both authenticated live checks passed. Restart FastAPI to apply.")
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
        print("  ⚠️  One or more authenticated live checks did not pass. See the measured result above.")
    print()
    return 0 if all_checks_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
