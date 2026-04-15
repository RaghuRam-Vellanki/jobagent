"""
Naukri Agent — scrapes Naukri.com for jobs.
Uses public search (no login needed for discovery).
"""
import re
import logging
from urllib.parse import urlencode, quote_plus

from .base_agent import BaseAgent

logger = logging.getLogger("agent.naukri")

BASE_URL = "https://www.naukri.com"


def _build_search_url(keyword: str, location: str, page: int = 1) -> str:
    kw_slug = keyword.lower().replace(" ", "-")
    loc_slug = location.lower().replace(" ", "-") if location and location.lower() != "india" else ""
    path = f"/{kw_slug}-jobs" + (f"-in-{loc_slug}" if loc_slug else "") + f"-{page}"
    return BASE_URL + path


class NaukriAgent(BaseAgent):
    platform = "naukri"

    async def login(self) -> bool:
        email = self.credentials.get("email", "")
        password = self.credentials.get("password", "")
        if not email or not password:
            logger.info("[Naukri] No credentials — skipping login (discovery only)")
            return True

        await self.page.goto("https://www.naukri.com/nlogin/login")
        await self.human_delay(2, 4)
        try:
            await self.page.fill("input[placeholder*='Email']", email)
            await self.human_delay(0.5, 1)
            await self.page.fill("input[type='password']", password)
            await self.human_delay(0.5, 1)
            await self.page.keyboard.press("Enter")
            await self.human_delay(3, 5)
            return "naukri.com" in self.page.url
        except Exception as e:
            logger.warning(f"[Naukri] Login failed: {e}")
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
            for page_num in range(1, 6):
                if len(jobs) >= max_jobs:
                    break
                url = _build_search_url(keyword, location, page_num)
                logger.info(f"[Naukri] Fetching: {url}")
                try:
                    await self.page.goto(url, wait_until="domcontentloaded")
                    await self.human_delay(2, 4)
                except Exception as e:
                    logger.warning(f"[Naukri] page load error: {e}")
                    break

                cards = await self.page.locator(
                    "article.jobTuple, .job-container, [data-job-id]"
                ).all()
                if not cards:
                    # Try alternate selectors
                    cards = await self.page.locator(".srp-jobtuple-wrapper, .list > li").all()
                if not cards:
                    logger.info(f"[Naukri] No cards on page {page_num} for '{keyword}'")
                    break

                logger.info(f"[Naukri] {len(cards)} cards — '{keyword}' page {page_num}")
                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    job = await self._parse_card(card)
                    if job:
                        jobs.append(job)
                    await self.human_delay(0.5, 1)

        return jobs

    async def _parse_card(self, card) -> dict | None:
        try:
            # Job ID
            job_id = await card.get_attribute("data-job-id") or \
                     await card.get_attribute("data-id")

            # Title
            title = ""
            for sel in [".title", "a.title", ".jobTitle", "h2 a", ".job-title"]:
                try:
                    title = (await card.locator(sel).first.inner_text()).strip()
                    if title:
                        break
                except Exception:
                    pass

            # Company
            company = ""
            for sel in [".comp-name", ".companyInfo span", ".subTitle", ".company-name"]:
                try:
                    company = (await card.locator(sel).first.inner_text()).strip()
                    if company:
                        break
                except Exception:
                    pass

            # Location
            location = ""
            for sel in [".locWdth", ".location", ".loc", ".jobLocation"]:
                try:
                    location = (await card.locator(sel).first.inner_text()).strip()
                    if location:
                        break
                except Exception:
                    pass

            # URL
            url = ""
            for sel in ["a.title", "a[href*='naukri.com/job']", "a[href*='-job-']"]:
                try:
                    href = await card.locator(sel).first.get_attribute("href")
                    if href:
                        url = href if href.startswith("http") else BASE_URL + href
                        break
                except Exception:
                    pass

            if not title:
                return None

            # Generate job_id from URL if not found
            if not job_id and url:
                m = re.search(r"-(\d+)\?", url)
                if m:
                    job_id = f"naukri_{m.group(1)}"
            if not job_id:
                import hashlib
                job_id = "naukri_" + hashlib.md5(title.encode() + (company or "").encode()).hexdigest()[:12]

            return {
                "job_id": job_id,
                "platform": "naukri",
                "title": title,
                "company": company or "Unknown",
                "location": location or "",
                "url": url,
                "description": "",   # fetched on demand
                "easy_apply": True,  # Naukri has its own "Apply" button
            }
        except Exception as e:
            logger.debug(f"[Naukri] parse_card error: {e}")
            return None

    async def get_description(self, url: str) -> str:
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            await self.human_delay(1.5, 3)
            for sel in [".job-desc", ".jd-desc", "#job_description", ".jobDescription"]:
                try:
                    text = await self.page.locator(sel).first.inner_text()
                    if len(text.strip()) > 100:
                        return text.strip()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[Naukri] get_description error: {e}")
        return ""

    async def apply_to_job(self, job: dict) -> str:
        """Naukri apply — opens job page, clicks Apply Now."""
        title = job.get("title", "?")
        url = job.get("url", "")
        if not url:
            return "skipped"
        try:
            await self.page.goto(url)
            await self.human_delay(2, 4)
            clicked = await self.safe_click("button#apply-button, a#apply-button, .apply-button")
            if clicked:
                await self.human_delay(2, 4)
                logger.info(f"[Naukri] Apply clicked: {title}")
                return "applied"
            return "skipped"
        except Exception as e:
            logger.error(f"[Naukri] apply error: {e}")
            return "failed"
