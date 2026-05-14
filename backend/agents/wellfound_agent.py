"""Wellfound (formerly AngelList Talent) agent — V1.3 Brief mode.

Public job-search scraping. Wellfound shows job cards on
`wellfound.com/jobs?q=<kw>&l=<loc>`. No login needed for discovery.

Cap at 20 cards per keyword to stay polite. Cards are React-rendered, so we
wait on `[data-test=JobSearchResults]` (their stable test hook).
"""
from __future__ import annotations

import logging
import hashlib

from .base_agent import BaseAgent

logger = logging.getLogger("agent.wellfound")

BASE_URL = "https://wellfound.com"


class WellfoundAgent(BaseAgent):
    platform = "wellfound"

    async def login(self) -> bool:
        # Public search needs no login.
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
            q = keyword.replace(" ", "%20")
            loc = (location or "India").replace(" ", "%20")
            url = f"{BASE_URL}/jobs?q={q}&l={loc}"
            logger.info(f"[wellfound] fetching {url}")
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self.human_delay(2, 4)
            except Exception as e:
                logger.warning(f"[wellfound] load error: {e}")
                continue

            # Scroll to load lazy cards
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
                await self.human_delay(1, 2)

            cards = await self.page.locator(
                "[data-test=JobSearchCard], [class*='styles_component']:has(a[href*='/jobs/'])"
            ).all()
            if not cards:
                cards = await self.page.locator("a[href*='/jobs/']").all()

            logger.info(f"[wellfound] {len(cards)} cards for '{keyword}'")
            for card in cards:
                if len(jobs) >= max_jobs:
                    break
                job = await self._parse_card(card)
                if job:
                    jobs.append(job)

        return jobs

    async def _parse_card(self, card) -> dict | None:
        try:
            title = ""
            for sel in ["[data-test=job-title]", "h3", "h2", "a[href*='/jobs/']"]:
                try:
                    title = (await card.locator(sel).first.inner_text()).strip()
                    if title:
                        break
                except Exception:
                    pass

            company = ""
            for sel in ["[data-test=startup-link]", "[class*='startup']", "h4"]:
                try:
                    company = (await card.locator(sel).first.inner_text()).strip()
                    if company:
                        break
                except Exception:
                    pass

            location = ""
            for sel in ["[data-test=job-location]", "[class*='location']"]:
                try:
                    location = (await card.locator(sel).first.inner_text()).strip()
                    if location:
                        break
                except Exception:
                    pass

            salary = ""
            try:
                salary = (await card.locator("[class*='salary'], [class*='comp']").first.inner_text()).strip()
            except Exception:
                pass

            url = ""
            try:
                href = await card.locator("a").first.get_attribute("href")
                if href:
                    url = href if href.startswith("http") else BASE_URL + href
            except Exception:
                pass

            if not title or len(title) < 3:
                return None

            job_id = "wellfound_" + hashlib.md5((title + (company or "")).encode()).hexdigest()[:12]

            return {
                "job_id": job_id,
                "platform": "wellfound",
                "title": title,
                "company": company or "Unknown",
                "location": location or "Remote",
                "url": url,
                "description": "",
                "salary": salary,
                "easy_apply": False,
                "apply_channel": "external",
            }
        except Exception as e:
            logger.debug(f"[wellfound] parse_card error: {e}")
            return None

    async def apply_to_job(self, job: dict) -> str:
        # Brief-only — apply path not implemented for V1.3.
        return "skipped"
