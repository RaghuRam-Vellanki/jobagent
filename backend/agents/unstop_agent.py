"""
Unstop (formerly D2C) Agent — scrapes Unstop for jobs and campus opportunities.
Great for BTech graduates and campus placements.
"""
import re
import logging
import hashlib

from .base_agent import BaseAgent

logger = logging.getLogger("agent.unstop")

BASE_URL = "https://unstop.com"


class UnstopAgent(BaseAgent):
    platform = "unstop"

    async def login(self) -> bool:
        email = self.credentials.get("email", "")
        password = self.credentials.get("password", "")
        if not email or not password:
            logger.info("[Unstop] No credentials — discovery only")
            return True

        await self.page.goto(f"{BASE_URL}/auth/sign-in")
        await self.human_delay(2, 3)
        try:
            await self.page.fill("input[type='email']", email)
            await self.page.fill("input[type='password']", password)
            await self.safe_click("button[type='submit']")
            await self.human_delay(3, 5)
            return "unstop.com" in self.page.url
        except Exception as e:
            logger.warning(f"[Unstop] Login failed: {e}")
            return False

    async def search_jobs(
        self,
        keywords: list[str],
        location: str,
        filters: dict,
        max_jobs: int = 40,
    ) -> list[dict]:
        jobs: list[dict] = []
        for keyword in keywords:
            if len(jobs) >= max_jobs:
                break
            url = f"{BASE_URL}/jobs?q={keyword.replace(' ', '%20')}"
            logger.info(f"[Unstop] Fetching: {url}")
            try:
                await self.page.goto(url, wait_until="domcontentloaded")
                await self.human_delay(2, 4)
            except Exception as e:
                logger.warning(f"[Unstop] load error: {e}")
                continue

            # Scroll to load more results
            for _ in range(3):
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await self.human_delay(1, 2)

            cards = await self.page.locator(
                ".opportunity-card, .job-card, [class*='JobCard'], [class*='job_card']"
            ).all()
            if not cards:
                cards = await self.page.locator("li[class*='card']").all()

            logger.info(f"[Unstop] {len(cards)} cards for '{keyword}'")
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
            for sel in [".title", "h2", ".job-title", "[class*='title']"]:
                try:
                    title = (await card.locator(sel).first.inner_text()).strip()
                    if title and len(title) > 3:
                        break
                except Exception:
                    pass

            company = ""
            for sel in [".org-name", ".company", "[class*='company']", "[class*='org']"]:
                try:
                    company = (await card.locator(sel).first.inner_text()).strip()
                    if company:
                        break
                except Exception:
                    pass

            location = ""
            for sel in ["[class*='location']", "[class*='city']"]:
                try:
                    location = (await card.locator(sel).first.inner_text()).strip()
                    if location:
                        break
                except Exception:
                    pass

            url = ""
            try:
                href = await card.locator("a").first.get_attribute("href")
                if href:
                    url = href if href.startswith("http") else BASE_URL + href
            except Exception:
                pass

            if not title:
                return None

            job_id = "unstop_" + hashlib.md5((title + (company or "")).encode()).hexdigest()[:12]

            return {
                "job_id": job_id,
                "platform": "unstop",
                "title": title,
                "company": company or "Unknown",
                "location": location or "India",
                "url": url,
                "description": "",
                "easy_apply": True,
            }
        except Exception as e:
            logger.debug(f"[Unstop] parse_card error: {e}")
            return None

    async def apply_to_job(self, job: dict) -> str:
        title = job.get("title", "?")
        url = job.get("url", "")
        if not url:
            return "skipped"
        try:
            await self.page.goto(url)
            await self.human_delay(2, 3)
            clicked = await self.safe_click("button[class*='apply'], a[class*='apply'], .apply-btn")
            if clicked:
                await self.human_delay(2, 4)
                logger.info(f"[Unstop] Apply clicked: {title}")
                return "applied"
            return "skipped"
        except Exception as e:
            logger.error(f"[Unstop] apply error: {e}")
            return "failed"
