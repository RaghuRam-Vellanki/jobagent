"""
Internshala Agent — scrapes Internshala for jobs and internships.
Best for freshers and BTech graduates.
"""
import re
import logging
import hashlib

from .base_agent import BaseAgent

logger = logging.getLogger("agent.internshala")

BASE_URL = "https://internshala.com"


class IntersthalaAgent(BaseAgent):
    platform = "internshala"

    async def login(self) -> bool:
        email = self.credentials.get("email", "")
        password = self.credentials.get("password", "")
        if not email or not password:
            logger.info("[Internshala] No credentials — discovery only")
            return True

        await self.page.goto(f"{BASE_URL}/login/user")
        await self.human_delay(2, 3)
        try:
            await self.page.fill("#modal_email", email)
            await self.page.fill("#modal_password", password)
            await self.safe_click("#modal_login_submit")
            await self.human_delay(2, 4)
            return "dashboard" in self.page.url or "internshala.com" in self.page.url
        except Exception as e:
            logger.warning(f"[Internshala] Login failed: {e}")
            return False

    async def search_jobs(
        self,
        keywords: list[str],
        location: str,
        filters: dict,
        max_jobs: int = 40,
    ) -> list[dict]:
        jobs: list[dict] = []
        # Internshala uses keyword in URL path
        for keyword in keywords:
            if len(jobs) >= max_jobs:
                break
            kw_slug = keyword.lower().replace(" ", "-")
            for page_num in range(1, 5):
                if len(jobs) >= max_jobs:
                    break
                url = f"{BASE_URL}/jobs/{kw_slug}/page-{page_num}"
                logger.info(f"[Internshala] Fetching: {url}")
                try:
                    await self.page.goto(url, wait_until="domcontentloaded")
                    await self.human_delay(2, 3)
                except Exception as e:
                    logger.warning(f"[Internshala] load error: {e}")
                    break

                cards = await self.page.locator(
                    ".individual_internship, .job_container, [data-internship_id]"
                ).all()
                if not cards:
                    logger.info(f"[Internshala] No cards on page {page_num} for '{keyword}'")
                    break

                logger.info(f"[Internshala] {len(cards)} cards — '{keyword}' page {page_num}")
                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    job = await self._parse_card(card)
                    if job:
                        jobs.append(job)

        return jobs

    async def _parse_card(self, card) -> dict | None:
        try:
            job_id = await card.get_attribute("data-internship_id") or \
                     await card.get_attribute("data-job_id") or \
                     await card.get_attribute("id")

            title = ""
            for sel in [".job-title", ".profile", "h3.job-internship-name", ".heading_4_5"]:
                try:
                    title = (await card.locator(sel).first.inner_text()).strip()
                    if title:
                        break
                except Exception:
                    pass

            company = ""
            for sel in [".company-name", ".company_name", ".heading_6"]:
                try:
                    company = (await card.locator(sel).first.inner_text()).strip()
                    if company:
                        break
                except Exception:
                    pass

            location = ""
            for sel in [".location_link", ".location", ".individual_internship_details span"]:
                try:
                    location = (await card.locator(sel).first.inner_text()).strip()
                    if location:
                        break
                except Exception:
                    pass

            url = ""
            for sel in ["a.job-title-href", "h3.job-internship-name a", "a[href*='/job/']", "a[href*='/internship/']"]:
                try:
                    href = await card.locator(sel).first.get_attribute("href")
                    if href:
                        url = href if href.startswith("http") else BASE_URL + href
                        break
                except Exception:
                    pass

            if not title:
                return None

            if not job_id:
                job_id = "is_" + hashlib.md5((title + (company or "")).encode()).hexdigest()[:12]
            else:
                job_id = f"internshala_{job_id}"

            return {
                "job_id": job_id,
                "platform": "internshala",
                "title": title,
                "company": company or "Unknown",
                "location": location or "Remote",
                "url": url,
                "description": "",
                "easy_apply": True,
            }
        except Exception as e:
            logger.debug(f"[Internshala] parse_card error: {e}")
            return None

    async def apply_to_job(self, job: dict) -> str:
        title = job.get("title", "?")
        url = job.get("url", "")
        if not url:
            return "skipped"
        try:
            await self.page.goto(url)
            await self.human_delay(2, 3)
            clicked = await self.safe_click("#continue_button, .apply_now_button, button.btn-primary")
            if clicked:
                await self.human_delay(2, 4)
                logger.info(f"[Internshala] Apply clicked: {title}")
                return "applied"
            return "skipped"
        except Exception as e:
            logger.error(f"[Internshala] apply error: {e}")
            return "failed"
