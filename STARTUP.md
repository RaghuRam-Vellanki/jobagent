# JobAgent — Run on a Fresh System

Copy-paste these steps on any new machine (Windows / macOS / Linux) to get JobAgent running end-to-end.

## Prerequisites (install once)

- **Python 3.11+** — https://www.python.org/downloads/  (tick "Add Python to PATH" on Windows)
- **Node.js 20+** — https://nodejs.org/
- **Git** — https://git-scm.com/

Verify in a new terminal:
```bash
python --version    # >= 3.11
node --version      # >= 20
git --version
```

## 1. Clone the repo

```bash
git clone https://github.com/RaghuRam-Vellanki/jobagent.git
cd jobagent
```

## 2. Backend — Python venv + deps + Playwright Chromium

### Windows (PowerShell or cmd)
```powershell
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
.venv\Scripts\python -m playwright install chromium
```

### macOS / Linux
```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m playwright install chromium
```

Playwright Chromium is ~220 MB; first install takes a minute or two.

## 3. Frontend — Node deps

```bash
cd frontend
npm install
cd ..
```

## 4. Environment variables (optional but recommended)

The agent works without these — but enabling the LLM screening-answer filler is what materially lifts callback rate. Without `ANTHROPIC_API_KEY`, custom screening questions get silent-skipped (incomplete applications).

### Windows (PowerShell — persisted to user env, opens new shells)
```powershell
setx ANTHROPIC_API_KEY "sk-ant-..."
setx LLM_DAILY_CAP_USD "1.50"     # optional, default 1.50
```
Close and reopen the terminal so the env var is picked up.

### macOS / Linux
```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc        # or ~/.bashrc
echo 'export LLM_DAILY_CAP_USD=1.50' >> ~/.zshrc
source ~/.zshrc
```

Get a key at https://console.anthropic.com/.

## 5. Launch

One command starts both servers, kills stale ports, and opens the browser:

```bash
python run.py
```

You should see:
- Backend on http://localhost:8000
- Frontend on http://localhost:5173 (auto-opens)

First run seeds the default profile in `data/jobs.db` and applies all schema migrations idempotently.

## 6. Sign in / set up your profile

1. Register a user on the login screen.
2. Open **Settings** → fill profile (full name, email, phone, current city, YoE, expected salary in LPA, notice period).
3. Upload your resume PDF (skills auto-extract).
4. Add LinkedIn + Naukri credentials (stored locally only; LinkedIn 2FA is manual on first login).
5. Pick **persona** (Fresher / Early-Career) and **preferred cities** (Bengaluru, Hyderabad, Delhi NCR, Remote-India, …).
6. Set daily caps (default 25 applies/day, 50 queue/day).

## 7. Run a discovery + apply cycle

1. **Discover Jobs** button on the Dashboard runs LinkedIn + Naukri + Top Companies in parallel.
2. Review the queue, click **Approve** on jobs you want.
3. **Apply** runs the Universal Form Filler against each approved job. For external company sites it follows the redirect, fills standard fields from your profile, and (with `ANTHROPIC_API_KEY`) answers custom screening questions via Claude Haiku — cached by question hash so identical questions across applications cost the LLM only once.
4. Per V1 default, the agent **stops at the review/submit page** — you click Submit. Flip "auto-submit" in Settings only after you've watched a few runs.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: sqlalchemy` | You ran `python backend/serve.py` with system Python. Use `.venv\Scripts\python backend\serve.py` (Win) or `.venv/bin/python backend/serve.py` (Unix). `run.py` does this for you. |
| Playwright "Executable doesn't exist" | Re-run `.venv\Scripts\python -m playwright install chromium`. |
| Port 5173 / 8000 already in use | `run.py` kills stale listeners automatically; if it doesn't, close other Vite/uvicorn windows. |
| LinkedIn 2FA loop | First login is always manual. The visible Chromium window stays open 120 s for you to complete 2FA; session cookies are then persisted. |
| `is_enabled: False` in LLM logs | `ANTHROPIC_API_KEY` not set in the shell that started `run.py`. Re-export and restart. |
| Reset everything | Delete `data/jobs.db` — schema is re-created on next startup. Your resume / `.env` are untouched. |

## Reset / clean

```bash
# Nuke the local DB (keeps resume + credentials in .env)
rm data/jobs.db        # macOS/Linux
del data\jobs.db       # Windows

# Reinstall Playwright if a Chromium update broke things
.venv\Scripts\python -m playwright install --force chromium
```

## What's where

```
backend/
  serve.py              # entry point — sets ProactorEventLoop on Windows then runs uvicorn
  main.py               # FastAPI app + lifespan (init_db)
  agents/
    universal_filler.py # the form-filler that runs against any apply page
    linkedin_agent.py   # LinkedIn search + Easy Apply + external-link follow
    naukri_agent.py     # Naukri search + Quick Apply + external
    ats_aggregator_agent.py  # Greenhouse + Ashby JSON discovery
  llm/
    claude_client.py    # Anthropic SDK wrapper, prompt caching, daily cap
    prompts.py          # screening + cover-letter prompt templates
  scoring/
    semantic_scorer.py  # persona/location/skill scoring
  db/
    models.py           # SQLAlchemy ORM
    database.py         # engine, _V1_COLUMNS migrations
  scheduler.py          # daily auto-run

frontend/src/
  pages/                # Dashboard, Queue, Applied, Settings, ATS, Onboarding
  store/agentStore.ts   # Zustand — single source of truth for agent phase + log
  hooks/useAgent.ts     # WebSocket → store

data/jobs.db            # SQLite DB (auto-created)
resume/                 # uploaded resume PDFs
context/                # project context, session notes
```

## One-liner for repeat machines

After the first machine is set up, the next one is just:

```bash
git clone https://github.com/RaghuRam-Vellanki/jobagent.git && cd jobagent && python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt && .venv/Scripts/python -m playwright install chromium && cd frontend && npm install && cd .. && python run.py
```

(Replace `.venv/Scripts/` with `.venv/bin/` on macOS/Linux.)
