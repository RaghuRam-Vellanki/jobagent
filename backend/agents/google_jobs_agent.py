"""Google Jobs agent — V1.3 Brief mode.

Scrapes the structured "jobs" widget that Google renders for queries like
`<role> jobs in <location>`. This catches postings on smaller company
career pages that LinkedIn/Naukri miss.

URL pattern: google.com/search?q=<kw>+jobs+<loc>&ibp=htl;jobs

No login. Headless. Polite delays. ~20 cards per keyword.
"""
from __future__ import annotations

import logging
import hashlib

from .base_agent import BaseAgent

logger = logging.getLogger("agent.google_jobs")


class GoogleJobsAgent(BaseAgent):
    platform = "google_jobs"

    async def login(self) -> bool:
        return True

    async def search_jobs(
        self,
        keywords: list[str],
        location: str,
        filters: dict,
        max_jobs: int = 20,
    ) -> list[dict]:
        jobs: list[dict] = []
        for keyword in keywords:
            if len(jobs) >= max_jobs:
                break
            q = f"{keyword} jobs {location or 'India'}".replace(" ", "+")
            url = f"https://www.google.com/search?q={q}&ibp=htl;jobs"
            logger.info(f"[google_jobs] fetching {url}")
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self.human_delay(2, 4)
            except Exception as e:
                logger.warning(f"[google_jobs] load error: {e}")
                continue

            # Scroll the inner jobs panel a few times to load more cards.
            for _ in range(3):
                await self.page.evaluate(
                    "document.querySelector('[role=main]')?.scrollBy(0, 800);"
                    "window.scrollBy(0, 800);"
                )
                await self.human_delay(1, 2)

            # Google rotates class names — try several stable-ish selectors.
            cards = await self.page.locator(
                "li[data-ved], div[role='treeitem'], li.iFjolb"
            ).all()
            if not cards:
                cards = await self.page.locator("[jsname][role='listitem']").all()

            logger.info(f"[google_jobs] {len(cards)} cards for '{keyword}'")
            for card in cards:
                if len(jobs) >= max_jobs:
                    break
                job = await self._parse_card(card, keyword)
                if job:
                    jobs.append(job)

        return jobs

    async def _parse_card(self, card, keyword: str) -> dict | None:
        try:
            text = ""
            try:
                text = await card.inner_text()
            except Exception:
                pass
            if not text or len(text) < 10:
                return None

            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            if not lines:
                return None

            title = lines[0]
            company = lines[1] if len(lines) > 1 else "Unknown"
            location = lines[2] if len(lines) > 2 else ""

            # Find an outbound link to the source job page.
            url = ""
            try:
                anchors = await card.locator("a").all()
                for a in anchors:
                    href = await a.get_attribute("href")
                    if href and href.startswith("http") and "google.com" not in href:
                        url = href
                        break
                if not url and anchors:
                    href = await anchors[0].get_attribute("href")
                    if href:
                        url = href if href.startswith("http") else "https://www.google.com" + href
            except Exception:
                pass

            if len(title) < 4 or "google" in title.lower():
                return None

            job_id = "gj_" + hashlib.md5((title + company).encode()).hexdigest()[:12]

            return {
                "job_id": job_id,
                "platform": "google_jobs",
                "title": title,
                "company": company,
                "location": location or "India",
                "url": url,
                "description": text[:800],
                "easy_apply": False,
                "apply_channel": "external",
            }
        except Exception as e:
            logger.debug(f"[google_jobs] parse_card error: {e}")
            return None

    async def apply_to_job(self, job: dict) -> str:
        return "skipped"
