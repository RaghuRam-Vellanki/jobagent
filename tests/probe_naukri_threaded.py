"""Reproduce the orchestrator's exact thread setup to isolate why
'Connection closed while reading from the driver' fires inside uvicorn
but not when run from main thread."""
import asyncio
import sys
import threading
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agents.naukri_agent import NaukriAgent

result = {"ok": False, "err": None, "n_jobs": 0}


def target():
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_agent())
        finally:
            loop.close()
    except Exception as e:
        result["err"] = f"{type(e).__name__}: {e}"


async def run_agent():
    agent = NaukriAgent(profile={}, credentials={})
    headless = not agent.requires_visible_browser
    print(f"[thread] starting browser headless={headless}")
    await agent.start(headless=headless)
    try:
        await agent.login()
        jobs = await agent.search_jobs(["Product Manager"], "India", {}, max_jobs=5)
        result["n_jobs"] = len(jobs)
        result["ok"] = True
    finally:
        await agent.stop()


t = threading.Thread(target=target, daemon=True, name="agent-test")
t.start()
t.join(timeout=120)
print(f"\nRESULT: {result}")
