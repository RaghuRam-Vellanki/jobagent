# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

JobAgent v2 — a multi-platform job hunting automation tool for LazyApply. It scrapes LinkedIn, Naukri, Internshala, and Unstop, scores jobs against a candidate's skills, queues matches for approval, then auto-applies via Playwright.

## Commands

### Starting the app
```bash
# Recommended: universal Python launcher (handles venv, deps, port cleanup, browser open)
python run.py

# Or directly (backend must use serve.py, NOT uvicorn directly — see critical note below)
python backend/serve.py          # backend on :8000
cd frontend && npm run dev       # frontend on :5173
```

### Backend only
```bash
# Always use serve.py, never `python -m uvicorn backend.main:app` directly on Windows
python backend/serve.py
```

### Frontend only
```bash
cd frontend
npm run dev       # dev server
npm run build     # production build (runs tsc first)
npm run preview   # preview production build
```

### Install dependencies
```bash
# Python
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt   # Windows
.venv/Scripts/python -m playwright install chromium     # downloads ~220 MB

# Node
cd frontend && npm install
```

### TypeScript check
```bash
cd frontend && npx tsc --noEmit
```

## Critical: Windows event loop

**Never start the backend with `python -m uvicorn backend.main:app` on Windows.** uvicorn uses `_WindowsSelectorEventLoop` which cannot spawn subprocesses. Playwright requires `ProactorEventLoop` to launch its Node.js bridge.

`backend/serve.py` exists solely to set `WindowsProactorEventLoopPolicy` before uvicorn starts. `run.py` and all `.bat`/`.ps1` launchers already call `backend/serve.py`. If you add new launch scripts, do the same.

The agent runs in a `threading.Thread` with its own `ProactorEventLoop` (see `_start_agent_thread` in `backend/api/agent.py`). WebSocket broadcasts from that thread use `asyncio.run_coroutine_threadsafe(..., _main_loop)` to post back to the uvicorn loop.

## Architecture

### Request / data flow
```
Browser → Vite dev (:5173) → proxy /api/* → FastAPI (:8000)
                                          → WebSocket /api/agent/ws (live log)
```

Vite proxies all `/api` traffic (HTTP + WebSocket) to `:8000`. The frontend never talks directly to the backend port.

### Backend (`backend/`)

| File | Purpose |
|------|---------|
| `serve.py` | Entry point. Sets ProactorEventLoop, then calls `uvicorn.run()` |
| `main.py` | FastAPI app, CORS, lifespan (`init_db()`), router includes |
| `config.py` | `TITLE_WHITELIST`, `TITLE_BLACKLIST`, path constants, env vars |
| `db/models.py` | SQLAlchemy ORM: `Job`, `DailyStats`, `Profile`, `Credential` |
| `db/database.py` | Engine, `SessionLocal`, `init_db()` (seeds default Raghuram profile on first run) |
| `api/agent.py` | Agent orchestrator — the most complex file. Shared `state` dict, WebSocket clients, threading, `_log()`, `_schedule_broadcast()` |
| `api/jobs.py` | CRUD for `Job` rows; `_job_to_dict()` converts comma-joined `matched_kws`/`ats_gaps` to arrays |
| `api/ats.py` | ATS scoring endpoint; `score_ats` uses resume text from DB |
| `scoring/semantic_scorer.py` | Pure keyword scorer. Returns `(score, matched_kws, skip_reason)`. Hard filters: title blacklist, title whitelist, company blacklist. Bonuses: +15 strong title, +10 Agile+PRD combo. Penalty: -20 for 3+ years required |
| `agents/base_agent.py` | Abstract Playwright base: browser lifecycle, `human_delay()`, `human_type()`, `safe_fill()`, `safe_click()` |
| `agents/linkedin_agent.py` | Full LinkedIn agent: manual/auto login, job scraping, Easy Apply form filling (inputs, radios, selects, file upload) |
| `agents/naukri_agent.py` | Naukri headless scraper |
| `agents/internshala_agent.py` | Internshala headless scraper |
| `agents/unstop_agent.py` | Unstop headless scraper |

**Agent state machine** (`state` dict in `api/agent.py`):
- `phase`: `idle → discovering → waiting → applying → idle`
- `running`: bool — agent thread reads this to know when to stop
- `paused`: bool — agent thread loops on `asyncio.sleep(2)` while True

**Job status flow**: `QUEUED → APPROVED → APPLIED` (or `SKIPPED`, `FAILED`)

### Frontend (`frontend/src/`)

| Path | Purpose |
|------|---------|
| `store/agentStore.ts` | Zustand store — single source of truth for agent phase/stats/log |
| `hooks/useAgent.ts` | WebSocket connection to `/api/agent/ws`; populates the Zustand store |
| `lib/api.ts` | Axios client with `baseURL: '/api'`; all API calls go here |
| `lib/types.ts` | `Job` interface — `matched_kws` and `ats_gaps` are `string[]` (backend splits comma-joined strings) |
| `pages/Dashboard.tsx` | Stats cards, AreaChart (weekly), PieChart (by platform), LiveLog |
| `pages/Queue.tsx` | QUEUED jobs with approve/reject |
| `pages/Applied.tsx` | Kanban status tracker |
| `pages/ATS.tsx` | Resume upload + JD paste → score ring |
| `pages/Settings.tsx` | Profile, credentials, search config, limits |
| `components/Sidebar.tsx` | Fixed 56px-wide nav; `ml-56` on main content |

**State flow**: WebSocket `init` message → `setAgentState({log, ...rest})` → Zustand → all components re-render. Subsequent `log` messages → `appendLog()`.

### Design tokens (Tailwind)
Custom colors: `bg`, `surface`, `border`, `text`, `muted`, `accent` (#0071e3), `success`, `warning`, `danger`. Platform colors: `linkedin`, `naukri`, `internshala`, `unstop`. Default `borderRadius` is 12px. Font: Inter.

## Database

SQLite at `data/jobs.db`. No migrations — `Base.metadata.create_all()` runs on every startup. To reset: delete `data/jobs.db`.

The default profile (Raghuram Vellanki, Product Owner) is seeded on first run in `init_db()`.

## Adding a new platform agent

1. Create `backend/agents/{platform}_agent.py` extending `BaseAgent`
2. Implement `login()`, `search_jobs()`, `apply_to_job()`
3. Add to `agent_classes` dict in `backend/api/agent.py`
4. Add platform color to `tailwind.config.ts` and `PlatformBadge.tsx`

## Known issues / design decisions

- **LinkedIn login is always manual** (`login_mode: "manual"`) — the user must log in within 120 seconds in the opened Chromium window. Auto-login with stored credentials is also supported but 2FA will fall back to manual.
- **No hot-reload for agents** — `--reload` mode reloads the uvicorn worker but the agent thread is separate; killing the server mid-discovery will orphan the Playwright browser process.
- **StrictMode removed** from `main.tsx` — was causing double WebSocket connections in development.
