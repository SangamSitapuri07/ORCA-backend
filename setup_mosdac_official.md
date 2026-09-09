# MOSDAC setup — use the OFFICIAL mdapi.py

Your login (zwiter07) is **not** the problem. The 3 Keycloak strategies
my code tries all fail because the form fields and CSRF tokens are
different from what I guessed.

**The right answer:** use MOSDAC's own official client. They wrote it,
they maintain it, it definitely works.

## Step 1 — Download mdapi.py from MOSDAC's website

In your PowerShell:

```powershell
cd $HOME\Desktop\orca-setup\SIH
mkdir mosdac_official
cd mosdac_official

# Download the official client
Invoke-WebRequest -Uri "https://www.mosdac.gov.in/software/mdapi.zip" -OutFile "mdapi.zip"

# Extract it
Expand-Archive mdapi.zip -DestinationPath .
```

You should now have `mdapi.py` and `config.json` in this folder.

## Step 2 — Fill in config.json

```powershell
notepad config.json
```

Replace the empty `username` and `password` with your real values:

```json
{
  "user_credentials": {
    "username": "zwiter07",
    "password": "YOUR_ACTUAL_PASSWORD"
  },
  "search_parameters": {
    "datasetId": "3SIMG_L1B_STD",
    "startTime": "2026-08-01",
    "endTime": "2026-08-15",
    "count": 1,
    "boundingBox": "70.0,8.0,90.0,28.0",
    "gId": ""
  },
  "download_settings": {
    "download_path": "./downloads",
    "organize_by_date": false,
    "skip_user_prompt": true,
    "generate_error_log": true,
    "error_log_path": "./error_logs"
  }
}
```

**Important:** `skip_user_prompt: true` so it doesn't ask you Y/N.

## Step 3 — Run it to confirm your account works

```powershell
python mdapi.py
```

If it logs in and says "Logout Successful. Goodbye zwiter07!" — your
account is good. The data will be in `./downloads/`.

If it says "Login failed" or your account is locked — wait 1 hour
(3 wrong attempts = 1 hour lockout), then try again with the right
password.

## Step 4 — Wire it into ORCA

Once `mdapi.py` works, we'll add a small wrapper to ORCA that calls
the same login function (we'll copy the login code from mdapi.py
into our pipeline). For now, just confirm step 3 works.

## Tell me what happens

Run step 3 and paste the output. If it succeeds, we'll wire it in
properly. If it fails, the error message will tell us exactly what's
wrong with your account.
