#Requires -Version 5.1
<#
ShieldMate: run the backend and the frontend together on WINDOWS (mirror of start.sh,
which is for macOS/Linux and needs lsof/python3/venv that this box doesn't have).

    .\start.ps1                  serve mode (the demo setup): build the frontend, then
                                 FastAPI serves the React app and /api together on :8000
    .\start.ps1 dev              dev mode: uvicorn on :8000 + the Vite dev server on
                                 :5173 (hot reload; Vite proxies /api to :8000)
    .\start.ps1 -Fresh           also delete the SQLite DB first (the backend recreates it)
    .\start.ps1 serve -NoBuild   serve mode only: reuse the existing frontend/dist

Run with:  powershell -ExecutionPolicy Bypass -File start.ps1   (or .\start.ps1)

Differences from start.sh (the macOS original, kept as-is):
  - no venv: uses `python` from PATH (Python 3.11 with fastapi/uvicorn); if the app
    imports are missing, requirements.txt is pip-installed into that interpreter
  - no lsof: port checks use netstat
  - Ctrl-C in dev mode kills both servers' process trees (taskkill /T)

The ports are fixed because frontend/vite.config.js hard-codes the proxy target
(http://localhost:8000) and the dev port (5173).
#>
param(
    [ValidateSet("serve", "dev")]
    [string]$Mode = "serve",
    [switch]$Fresh,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$Root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$BackendPort = 8000
$FrontendPort = 5173

function info($m) { Write-Host "[" + "shieldmate" + "] " $m -ForegroundColor Cyan }
function warn($m) { Write-Host "[shieldmate] warning: " $m -ForegroundColor Yellow }
function die($m)  { Write-Host "[shieldmate] error: " $m -ForegroundColor Red; exit 1 }
function usage() {
    Write-Host "Usage: start.ps1 [serve|dev] [-Fresh] [-NoBuild]"
    Write-Host "  serve         build the frontend and serve everything from FastAPI on :$BackendPort (default)"
    Write-Host "  dev           uvicorn on :$BackendPort + Vite dev server on :$FrontendPort (hot reload)"
    Write-Host "  -Fresh        delete the SQLite database before starting"
    Write-Host "  -NoBuild      serve mode: skip the frontend build and reuse frontend/dist"
}

# --- preflight -----------------------------------------------------------------

function Find-Tool([string]$name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    die "'$name' is not installed or not on PATH"
}

function Test-PortBusy([int]$Port, [string]$What) {
    # netstat -a (no Windows replacement for lsof here). Any LISTENING line on the port.
    $listeners = netstat -ano | Select-String -Pattern (":$Port\s") | Select-String -Pattern "LISTENING"
    if ($listeners) {
        $listeners | ForEach-Object { Write-Host $_.Line.Trim() -ForegroundColor Yellow }
        die "port $Port ($What) is already in use. Stop that process first (see above)."
    }
}

function Get-LanIp {
    # The address a phone on the same network would use (ipconfig parse; first non-loopback IPv4).
    $ip = ""
    $lines = ipconfig 2>$null
    foreach ($l in $lines) {
        if ($l -match 'IPv4 Address[^\d]*(\d+\.\d+\.\d+\.\d+)') {
            $ip = $Matches[1]
            if ($ip.StartsWith("127.") -or $ip.StartsWith("169.254.")) { $ip = "" }
            if ($ip) { break }
        }
    }
    $ip
}

function Show-Banner([int]$Port) {
    $ip = Get-LanIp
    Write-Host ""
    info "ShieldMate is starting in $Mode mode"
    Write-Host "    This computer : http://localhost:$Port"
    if ($ip) { Write-Host "    Phones (same network) : http://${ip}:${Port}" }
    Write-Host "    Pages         : /  (pick a person)   /owner   /it   /mission   /backstage"
    Write-Host "    Backend health: http://localhost:$BackendPort/api/status"
    Write-Host "    Reset demo    : POST /api/demo/reset  (or make reset)"
    Write-Host ""
}

# --- backend environment -------------------------------------------------------

function Ensure-BackendEnv {
    # No venv on this box: call the Python on PATH (3.11 with fastapi/uvicorn).
    $script:Python = $null
    foreach ($c in @("python", "py", "python3")) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) { $script:Python = $cmd.Source; break }
    }
    if (-not $script:Python) { die "python not found on PATH; install Python 3.11+ first" }
    # Only install when the app's imports are missing, so repeat starts stay fast.
    & $script:Python -c "import fastapi, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        info "Installing backend requirements"
        & $script:Python -m pip install --quiet -r "$Backend\requirements.txt"
        if ($LASTEXITCODE -ne 0) { die "pip install failed; check the output above" }
    }
    if (-not (Test-Path "$Backend\.env")) {
        info "backend/.env not found: using built-in defaults (replay mode, flags off)"
    }
}

# --- frontend dependencies and build --------------------------------------------

function Ensure-FrontendDeps {
    # node_modules missing means a fresh clone; npm ci installs exactly the lockfile.
    if (-not (Test-Path "$Frontend\node_modules")) {
        info "Installing frontend dependencies (npm ci)"
        Push-Location $Frontend
        try { & (Find-Tool "npm") ci; if ($LASTEXITCODE -ne 0) { die "npm ci failed; check the output above" } }
        finally { Pop-Location }
    }
}

function Build-Frontend {
    # Always rebuild by default, so the served app matches the source.
    info "Building the frontend"
    Push-Location $Frontend
    try { & (Find-Tool "npm") run build; if ($LASTEXITCODE -ne 0) { die "frontend build failed" } }
    finally { Pop-Location }
}

# --- fresh start ---------------------------------------------------------------

function Reset-Database {
    # DB_PATH (env var) overrides the default; a value in backend/.env is not read here.
    $db = $env:DB_PATH
    if (-not $db) { $db = "backend\shieldmate.db" }
    if (-not [IO.Path]::IsPathRooted($db)) { $db = Join-Path $Root $db }
    info "Removing database $db (and its -wal/-shm files)"
    foreach ($f in @($db, "$db-wal", "$db-shm")) {
        if (Test-Path $f) { Remove-Item $f -Force }
    }
}

# --- serve mode ----------------------------------------------------------------

function Run-Serve {
    Find-Tool "node" | Out-Null; Find-Tool "npm" | Out-Null   # fail early like check_tools
    Test-PortBusy $BackendPort "backend + built frontend"
    Ensure-BackendEnv
    Ensure-FrontendDeps
    if ($Fresh) { Reset-Database }
    if (-not $NoBuild) {
        Build-Frontend
    } else {
        if (-not (Test-Path "$Frontend\dist\index.html")) {
            die "-NoBuild was given but frontend/dist does not exist; run without -NoBuild"
        }
    }
    Show-Banner $BackendPort
    # One worker and no --reload: the background loops (action timeouts, Wazuh polling,
    # sim ingest) must run exactly once.
    Push-Location $Backend
    try { & $script:Python -m uvicorn main:app --host 0.0.0.0 --port $BackendPort }
    finally { Pop-Location }
}

# --- dev mode -------------------------------------------------------------------

function Run-Dev {
    Find-Tool "node" | Out-Null; Find-Tool "npm" | Out-Null
    Test-PortBusy $BackendPort "backend"
    Test-PortBusy $FrontendPort "Vite dev server"
    Ensure-BackendEnv
    Ensure-FrontendDeps
    if ($Fresh) { Reset-Database }

    $npm = Find-Tool "npm"
    info "Starting the backend on :$BackendPort"
    # -NoNewWindow: both servers' output stays in this terminal; -PassThru: we can kill them.
    $backendProc = Start-Process -FilePath $script:Python `
        -ArgumentList @("-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$BackendPort") `
        -WorkingDirectory $Backend -NoNewWindow -PassThru

    # Block until the backend answers, so Vite never opens against a dead proxy target.
    $up = $false
    for ($i = 0; $i -lt 30; $i++) {
        try { Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/status" -TimeoutSec 1 | Out-Null; $up = $true; break } catch { }
        if ($backendProc.HasExited) { die "the backend exited during start-up (see its output above)" }
        Start-Sleep -Milliseconds 500
    }
    if (-not $up) { die "the backend did not answer /api/status within 15 seconds" }

    info "Starting the Vite dev server on :$FrontendPort"
    # --strictPort: fail instead of silently picking another port (the preflight already checked).
    $frontProc = Start-Process -FilePath $npm `
        -ArgumentList @("run", "dev", "--", "--strictPort") `
        -WorkingDirectory $Frontend -NoNewWindow -PassThru

    Show-Banner $FrontendPort

    # Stay in the foreground until either server stops. Ctrl-C (or an exit) kills both
    # process trees: npm -> sh -> node would otherwise be left behind.
    try {
        while (-not $backendProc.HasExited -and -not $frontProc.HasExited) {
            $backendProc.Refresh(); $frontProc.Refresh()
            Start-Sleep -Seconds 1
        }
    } finally {
        # Ctrl-C (or an exit): kill both process trees, or npm -> sh -> node would linger.
        foreach ($p in @($frontProc, $backendProc)) {
            if ($p -and -not $p.HasExited) {
                taskkill /PID $p.Id /T /F | Out-Null
            }
        }
    }
    if (-not $backendProc.HasExited) { die "the Vite dev server stopped unexpectedly" }
    die "the backend stopped unexpectedly"
}

switch ($Mode) {
    "serve" { Run-Serve }
    "dev"   { Run-Dev }
}
