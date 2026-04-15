#!/usr/bin/env bash
# ================================================
# JobAgent v2 — One-command launcher
# Usage: bash start.sh
# ================================================
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║      JobAgent v2 — LazyApply     ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── 1. Python venv ────────────────────────────────────────────────────
if [ ! -d "$ROOT/.venv" ]; then
  echo "▸ Creating Python virtual environment..."
  python -m venv "$ROOT/.venv"
fi

source "$ROOT/.venv/Scripts/activate" 2>/dev/null || source "$ROOT/.venv/bin/activate"

echo "▸ Installing Python dependencies..."
pip install -q -r "$BACKEND/requirements.txt"

echo "▸ Installing Playwright browsers..."
playwright install chromium 2>/dev/null || python -m playwright install chromium

# ── 2. Node dependencies ─────────────────────────────────────────────
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "▸ Installing Node dependencies..."
  cd "$FRONTEND" && npm install --silent
  cd "$ROOT"
fi

# ── 3. Copy .env if missing ──────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "▸ Created .env from .env.example"
fi

# ── 4. Launch backend + frontend ─────────────────────────────────────
echo ""
echo "▸ Starting backend  → http://localhost:8000"
echo "▸ Starting frontend → http://localhost:5173"
echo ""
echo "  Dashboard: http://localhost:5173"
echo "  API docs:  http://localhost:8000/docs"
echo ""

# Start backend in background
cd "$BACKEND"
uvicorn main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ''; echo 'Stopped.'" INT TERM
wait
