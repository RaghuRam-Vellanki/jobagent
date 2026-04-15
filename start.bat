@echo off
setlocal enabledelayedexpansion
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo.
echo   ==========================================
echo      JobAgent v2  --  LazyApply
echo   ==========================================
echo.

:: ── Kill any existing processes on our ports ─────────────────────────
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 "') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: ── 1. Python venv ────────────────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo  ERROR: Python not found.
        echo  Install Python 3.11+ from https://python.org and try again.
        echo.
        pause & exit /b 1
    )
)

:: ── 2. Python dependencies ───────────────────────────────────────────
echo [2/4] Installing Python dependencies...
call ".venv\Scripts\activate.bat"
pip install -q -r backend\requirements.txt
echo      Installing Playwright Chromium...
python -m playwright install chromium >nul 2>&1

:: ── 3. Node dependencies ─────────────────────────────────────────────
if not exist "frontend\node_modules\vite" (
    echo [3/4] Installing Node dependencies...
    cd frontend
    npm install --silent
    cd ..
) else (
    echo [3/4] Node dependencies OK.
)

:: ── 4. .env ──────────────────────────────────────────────────────────
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo      Created .env
)

:: ── 5. Write helper scripts then launch ─────────────────────────────
echo [4/4] Launching servers...

:: Write backend launcher to a temp file (avoids %~dp0 quoting hell)
set "BSCRIPT=%TEMP%\ja_backend.bat"
(
    echo @echo off
    echo title JobAgent Backend
    echo cd /d "%ROOT%"
    echo call ".venv\Scripts\activate.bat"
    echo echo Backend starting on http://localhost:8000 ...
    echo python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
    echo pause
) > "%BSCRIPT%"

set "FSCRIPT=%TEMP%\ja_frontend.bat"
(
    echo @echo off
    echo title JobAgent Frontend
    echo cd /d "%ROOT%frontend"
    echo echo Frontend starting on http://localhost:5173 ...
    echo npm run dev
    echo pause
) > "%FSCRIPT%"

start "JobAgent Backend"  cmd /c "%BSCRIPT%"
timeout /t 3 /nobreak >nul
start "JobAgent Frontend" cmd /c "%FSCRIPT%"
timeout /t 4 /nobreak >nul

echo.
echo   Backend   --^>  http://localhost:8000
echo   Frontend  --^>  http://localhost:5173
echo   API docs  --^>  http://localhost:8000/docs
echo.

start http://localhost:5173

echo  Both servers are running in separate windows.
echo  Close those windows to stop the agent.
echo.
pause
