"""
Windows-safe uvicorn launcher.
Must set ProactorEventLoop BEFORE uvicorn starts — Playwright needs it to
spawn its Node.js subprocess (SelectorEventLoop raises NotImplementedError).
"""
import sys
import os
import asyncio

# ── Ensure both project root and backend/ are on sys.path ──────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))       # .../jobagent/backend
_ROOT = os.path.dirname(_HERE)                           # .../jobagent
for p in (_ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Windows: force ProactorEventLoop so Playwright can spawn subprocesses ──
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn  # noqa: E402 — import AFTER policy is set

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[_HERE],
        log_level="info",
    )
