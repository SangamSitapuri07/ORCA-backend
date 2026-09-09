# ORCA pipeline — data layer

This package contains everything that talks to external data sources:
MOSDAC (ISRO satellite data), INCOIS (operational ocean advisories), and
the file parsers that turn raw NetCDF / HDF5 into values we can use.

## Files

| File | What it does |
| --- | --- |
| `mosdac_auth.py` | Login to MOSDAC via Keycloak SSO, return a `requests.Session` with the bearer token attached |
| `parser.py`       | Open NetCDF4 / HDF5 files, extract lat/lon + 2D variables into plain dicts |
| `mosdac_search.py` | (coming next) Search for available files by dataset + date + bounding box |
| `mosdac_download.py` | (coming next) Download a file to local disk with progress reporting |
| `incois.py`        | (later) Pull operational advisories from INCOIS |

## Setup (one time, locally)

```bash
# 1. Create a fresh venv for the pipeline
cd /path/to/SIH
python3 -m venv .pipeline-venv
source .pipeline-venv/bin/activate
pip install requests xarray netCDF4 h5py numpy

# 2. Set your MOSDAC credentials
export MOSDAC_USERNAME="your_username"
export MOSDAC_PASSWORD="your_password"

# 3. Test the login
python -m pipeline.mosdac_auth
```

If you see `✅ Auth works.`, we're good to move on to search + download.
If you see `❌ Login failed:`, read the message — usually it's a typo or
a not-yet-approved account.

## Important: never commit your password

The `mosdac_auth.py` module reads credentials from environment variables
only. There are no defaults, no fallbacks, no config files. If you forget
to set them, it will refuse to run with a clear error message.

If you accidentally paste a password into chat, change it immediately on
https://mosdac.gov.in — they have a password reset flow.

## What we'll build next

1. **`mosdac_search.py`** — given a `datasetId` and date range, list the
   files we could download. Test on a known public dataset first.

2. **`mosdac_download.py`** — download a file by ID, save it to a
   `data/` directory, print a progress bar. Use the same config.json
   style as MOSDAC's official `mdapi.py`.

3. **`mosdac_parse.py`** (extends `parser.py`) — domain-specific
   extractors for chlorophyll / SST / wind, returning clean Python
   objects we can pass to the backend agents.

4. **`cache.py`** — store parsed values in a local SQLite so we don't
   re-download 50MB files every time the user asks a question.

5. **Replace the mock data** in `backend/app/data/` with these real
   adapters, keep the agent code unchanged.

## Status

| Component | Status |
| --- | --- |
| `mosdac_auth.py` | ✅ Written, awaiting first live test with your creds |
| `parser.py`      | ✅ Written, testable on any open NetCDF file |
| `mosdac_search.py`  | ⏳ Next, after auth confirmed |
| `mosdac_download.py` | ⏳ After search |
| `cache.py`        | ⏳ After first successful download |
| Replace mocks in backend | ⏳ After we have 1–2 real datasets flowing |
