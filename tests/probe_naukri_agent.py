"""Smoke test for the rewritten NaukriAgent — no uvicorn, no auth, no DB."""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Add backend to path
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agents.naukri_agent import NaukriAgent


async def main():
    agent = NaukriAgent(profile={}, credentials={})
    # Honor the agent's headless preference
    headless = not agent.requires_visible_browser
    print(f"Starting browser (headless={headless})")
    await agent.start(headless=headless)
    try:
        ok = await agent.login()
        print(f"login() returned {ok}")
        jobs = await agent.search_jobs(
            keywords=["Product Manager"],
            location="India",
            filters={},
            max_jobs=10,
        )
        print(f"\nGot {len(jobs)} jobs.")
        for j in jobs[:5]:
            print(f"  - [{j['job_id']}] {j['title']} @ {j['company']} ({j['location']}) {j['experience']}")
            print(f"    {j['url']}")
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
