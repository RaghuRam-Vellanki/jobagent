# JobAgent v2 — PowerShell launcher
# Usage: Right-click -> Run with PowerShell  OR  pwsh -File start.ps1

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor Cyan
Write-Host "     JobAgent v2  --  LazyApply" -ForegroundColor Cyan
Write-Host "  ==========================================" -ForegroundColor Cyan
Write-Host ""

# Kill anything on port 8000
$proc = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($proc) { Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue }

# 1. Python venv
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[1/4] Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Python not found. Install Python 3.11+ from https://python.org" -ForegroundColor Red
        Read-Host "Press Enter to exit"; exit 1
    }
}

# 2. Python deps
Write-Host "[2/4] Installing Python dependencies..." -ForegroundColor Yellow
& ".venv\Scripts\activate.ps1"
pip install -q -r backend\requirements.txt
python -m playwright install chromium 2>$null

# 3. Node deps
if (-not (Test-Path "frontend\node_modules\vite")) {
    Write-Host "[3/4] Installing Node dependencies..." -ForegroundColor Yellow
    Set-Location frontend; npm install --silent; Set-Location $Root
} else {
    Write-Host "[3/4] Node dependencies OK." -ForegroundColor Green
}

# 4. .env
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

# 5. Launch servers
Write-Host "[4/4] Starting servers..." -ForegroundColor Yellow

$backendScript = {
    param($root)
    Set-Location $root
    & ".venv\Scripts\activate.ps1"
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
}

$frontendScript = {
    param($root)
    Set-Location "$root\frontend"
    npm run dev
}

Start-Process pwsh -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; & '.venv\Scripts\Activate.ps1'; python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload" -WindowStyle Normal
Start-Sleep 3
Start-Process pwsh -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; npm run dev" -WindowStyle Normal
Start-Sleep 4

Write-Host ""
Write-Host "  Backend   -->  http://localhost:8000" -ForegroundColor Green
Write-Host "  Frontend  -->  http://localhost:5173" -ForegroundColor Green
Write-Host "  API docs  -->  http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""

Start-Process "http://localhost:5173"

Write-Host "Both servers running in separate windows. Close them to stop." -ForegroundColor Cyan
Read-Host "Press Enter to exit this launcher"
