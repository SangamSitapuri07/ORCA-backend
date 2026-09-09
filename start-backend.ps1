# ORCA backend - clean-start script for Windows
# ---------------------------------------------
# Why this exists:
#   On Windows, two uvicorn processes CAN silently share port 8000
#   (SO_REUSEADDR). Then every other request goes to a stale/zombie
#   backend and Next.js shows "socket hang up". This script kills any
#   stale listener first, then starts ONE fresh backend.
#
# NOTE: keep this file PURE ASCII (no em-dashes / emoji). Windows
# PowerShell 5.1 reads UTF-8 .ps1 files without BOM as ANSI, and some
# multi-byte characters then corrupt the parser.
#
# Run from PowerShell:
#   cd C:\Users\sanga\Desktop\orca-setup\SIH
#   .\start-backend.ps1
#
# If execution policy blocks it:
#   powershell -ExecutionPolicy Bypass -File .\start-backend.ps1

$ErrorActionPreference = "Stop"

Write-Host "[ORCA] Step 1/4: checking port 8000 for stale backends..."

# 1) Kill whatever is listening on port 8000 (stale backends)
$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conns) {
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pids) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host ("[ORCA] Killing stale listener on :8000 -> " + $proc.ProcessName + " (pid " + $p + ")")
            Stop-Process -Id $p -Force
            Start-Sleep -Seconds 1
        }
    }
} else {
    Write-Host "[ORCA] Port 8000 is free."
}

# 2) Show which code we are actually running (must say b0dfcfd or newer)
Write-Host ""
Write-Host "[ORCA] Step 2/4: code version:"
git -C $PSScriptRoot log -1 --oneline

# 3) Activate the venv that lives next to the repo (orca-setup\.venv)
$venv = Join-Path $PSScriptRoot "..\.venv\Scripts\Activate.ps1"
if (Test-Path $venv) {
    . $venv
    Write-Host ("[ORCA] Step 3/4: venv activated: " + $venv)
} else {
    Write-Host ("[ORCA] WARNING: venv not found at " + $venv + " - using system python")
}

# 4) Sanity: python can import the app BEFORE we burn time
Set-Location $PSScriptRoot
Write-Host "[ORCA] Step 4/4: verifying import..."
python -c "import backend.main; print('[ORCA] import OK - version ' + backend.main.app.version)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ORCA] Import failed - fix the error above before starting."
    exit 1
}

# 5) Start the backend. -X faulthandler = print Python stack even on a
#    native crash; backend/main.py also appends it to logs\orca-fault.log
Write-Host ""
Write-Host "[ORCA] Starting on http://127.0.0.1:8000  (Ctrl+C to stop)"
Write-Host ""
python -X faulthandler -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
