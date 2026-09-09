# ORCA — How to run the full stack

This is the short, copy-paste guide to get the whole ORCA stack running
on your machine. Two terminals. 5 minutes.

## Prerequisites

- Python 3.11+ (you have it — your venv is at `.venv/`)
- Node 18+ (you have it — used to create `web/`)
- Your GFW API token (you have it)
- Internet that can reach coastwatch.noaa.gov, marine-api.open-meteo.com, gateway.api.globalfishingwatch.org

## One-time setup (5 min, then never again)

```powershell
# 1. Pull latest
cd $HOME\Desktop\orca-setup\SIH
git pull

# 2. Install Python dependencies into your venv
#    (your venv uses Scripts/python.exe and may not have a separate pip.exe)
python -m pip install fastapi 'uvicorn[standard]' pydantic
python -m pip install -r pipeline/requirements.txt
```

`pipeline/requirements.txt` already lists xarray, netCDF4, numpy, etc.

## Credentials (.env file — recommended)

Put your API tokens in a `.env` file once. The backend and pipeline
auto-load it on startup. OS env vars always take precedence.

```powershell
# Create the .env file in the project root
cd $HOME\Desktop\orca-setup\SIH
notepad .env
```

Paste this (replace with your real values — don't paste them in chat):

```
GFW_API_TOKEN=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.your_full_token_here
MOSDAC_USERNAME=your.email@example.com
MOSDAC_PASSWORD=your_mosdac_password
```

Save and close. The backend will pick these up automatically. You can
also verify they're loaded by running:

```powershell
python tools/verify_credentials.py
```

## Run the full stack

### Terminal 1 — FastAPI backend (port 8000)

```powershell
cd $HOME\Desktop\orca-setup\SIH
python -m uvicorn backend.main:app --port 8000
```

(If you'd rather use shell env vars, the old way still works:
`$env:GFW_API_TOKEN = "..."; $env:MOSDAC_USERNAME = "..."; ...`)

You should see:
```
INFO:     Started server process [...]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Terminal 2 — Next.js dashboard (port 3000)

```powershell
cd $HOME\Desktop\orca-setup\SIH\web

# First time only: install node packages (may take 1-2 minutes)
npm install --legacy-peer-deps

# Then start the dev server
npm run dev
```

You should see:
```
▲ Next.js 14.2.35
- Local:        http://localhost:3000
✓ Ready in 1s
```

> The `--legacy-peer-deps` flag is needed because `react-leaflet@4` has
> a peer-dep on React 17, and Next 14 ships React 18. The flag tells
> npm to accept the mismatch.

## Open the dashboard

Browser → **http://localhost:3000**

- You'll see a map of India with 8 markers (Mumbai, Goa, Cochin, Chennai, Vizag, Kandla, Andaman, Lakshadweep)
- Click any marker → side panel shows full multi-agent analysis
- Backend logs each request to Terminal 1

## Quick sanity check (one command, no browser)

```powershell
# In a third terminal, or in browser
curl http://localhost:3000/api/v1/health
# Should return JSON with status: "ok"
```

## What's wired up

```
Browser (3000) → Next.js → /api/* proxy → FastAPI (8000) → Python pipeline
                                                                ↓
                                                            6 satellite/AIS APIs:
                                                              NOAA chlorophyll (🇺🇸)
                                                              ESA OC-CCI  (🇪🇺)
                                                              Open-Meteo Marine
                                                              Open-Meteo Weather
                                                              Global Fishing Watch
                                                              MOSDAC OCM-3 (🇮🇳)
                                                                ↓
                                                            10 AI agents
```

## Common issues

| Error | Fix |
|-------|-----|
| `No module named uvicorn` | Run the pip install step above |
| `port 8000 already in use` | Kill the old uvicorn: `Get-Process -Name "python" \| Where-Object {$_.Path -like "*uvicorn*"} \| Stop-Process` |
| `port 3000 already in use` | Same but for `node` |
| `No data returned` | Check the Terminal 1 logs; one or more data sources may be down |
| `GFW_API_TOKEN not set` | Check `python tools/verify_credentials.py` to see what's missing from `.env` |
| `ECONNREFUSED 127.0.0.1:8000` | Terminal 1 isn't running, or crashed |
| `HTTP 401 from GFW` | Token is wrong. Re-copy from https://globalfishingwatch.org/our-apis/tokens/ |
| `HTTP 401 from MOSDAC` | Username/password wrong, or account locked (1 hour cooldown after 3 fails) |
