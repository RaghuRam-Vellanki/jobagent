"""
LinkedIn Agent — Playwright rewrite of v1 Selenium agent.
Supports agentic mode (visible browser, manual login) and headless scraping.
"""
import re
import random
import logging
import os
from urllib.parse import urlencode
from playwright.async_api import TimeoutError as PWTimeout

from .base_agent import BaseAgent

logger = logging.getLogger("agent.linkedin")


def _build_search_url(keyword: str, location: str, date_posted: str, start: int = 0) -> str:
    params = {
        "keywords": keyword,
        "location": location,
        "f_TPR": date_posted,
        "f_LF": "f_AL",   # Easy Apply only
        "start": start,
    }
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def _extract_job_id(text: str) -> str | None:
    for pat in [r"currentJobId=(\d+)", r"/jobs/view/(\d+)", r"(\d{8,})"]:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


class LinkedInAgent(BaseAgent):
    platform = "linkedin"

    async def login(self) -> bool:
        email = self.credentials.get("email", "")
        password = self.credentials.get("password", "")
        login_mode = self.credentials.get("login_mode", "manual")

        await self.page.goto("https://www.linkedin.com/login")
        await self.human_delay(2, 4)

        if login_mode == "manual":
            logger.info("[LinkedIn] Manual login — complete in 120s...")
            try:
                await self.page.wait_for_url("**/feed**", timeout=120_000)
                logger.info("[LinkedIn] Manual login complete.")
                return True
            except PWTimeout:
                logger.error("[LinkedIn] Manual login timed out.")
                return False

        try:
            await self.page.fill("#username", email)
            await self.human_delay(0.5, 1.5)
            await self.page.fill("#password", password)
            await self.human_delay(0.5, 1.5)
            await self.page.keyboard.press("Enter")
            await self.human_delay(3, 6)
            if "feed" in self.page.url:
                logger.info("[LinkedIn] Auto login success.")
                return True
            # 2FA fallback
            await self.page.wait_for_url("**/feed**", timeout=120_000)
            return True
        except Exception as e:
            logger.error(f"[LinkedIn] Login failed: {e}")
            return False

    async def search_jobs(
        self,
        keywords: list[str],
        location: str,
        filters: dict,
        max_jobs: int = 40,
    ) -> list[dict]:
        date_posted = filters.get("date_posted", "r86400")
        jobs: list[dict] = []

        for keyword in keywords:
            if len(jobs) >= max_jobs:
                break
            start = 0
            while len(jobs) < max_jobs:
                url = _build_search_url(keyword, location, date_posted, start)
                await self.page.goto(url)
                await self.human_delay(3, 5)

                cards = await self._get_job_cards()
                if not cards:
                    logger.info(f"[LinkedIn] No more cards for '{keyword}'")
                    break

                logger.info(f"[LinkedIn] {len(cards)} cards — keyword='{keyword}' start={start}")

                for card in cards:
                    if len(jobs) >= max_jobs:
                        break
                    job = await self._process_card(card)
                    if job:
                        jobs.append(job)
                    await self.human_delay(1, 2)

                start += 25
                if start >= 175:
                    break
                await self.human_delay(2, 4)

        return jobs

    async def _get_job_cards(self) -> list:
        await self.page.wait_for_timeout(2000)
        for sel in [
            ".jobs-search-results__list-item",
            ".scaffold-layout__list-item",
            "[data-occludable-job-id]",
        ]:
            cards = await self.page.locator(sel).all()
            if cards:
                return cards
        return []

    async def _process_card(self, card) -> dict | None:
        try:
            # Get job_id from attribute
            job_id = await card.get_attribute("data-occludable-job-id") or \
                     await card.get_attribute("data-job-id")

            # Extract visible metadata
            title = await self._card_text(card, [
                "a.job-card-list__title--link",
                "a.job-card-list__title",
                ".artdeco-entity-lockup__title",
            ])
            company = await self._card_text(card, [
                ".job-card-container__primary-description",
                ".artdeco-entity-lockup__subtitle",
            ])
            location = await self._card_text(card, [
                ".job-card-container__metadata-item",
                ".artdeco-entity-lockup__caption",
            ])

            # Click to open detail panel
            await card.scroll_into_view_if_needed()
            await self.human_delay(0.3, 0.7)
            try:
                link = card.locator("a[href*='/jobs/view/']").first
                await link.click()
            except Exception:
                await card.click()
            await self.human_delay(2, 3.5)

            url = self.page.url
            if not job_id:
                job_id = _extract_job_id(url)
            if not job_id:
                return None

            description = await self._get_description()
            easy_apply = await self._has_easy_apply()

            # Fallback title/company from detail panel
            if not title:
                title = await self.get_text("h1.t-24, .job-details-jobs-unified-top-card__job-title h1")
            if not company:
                company = await self.get_text(
                    ".job-details-jobs-unified-top-card__company-name a, "
                    ".jobs-unified-top-card__company-name a"
                )

            return {
                "job_id": job_id,
                "platform": "linkedin",
                "title": title or "Unknown",
                "company": company or "Unknown",
                "location": location or "",
                "url": url,
                "description": description,
                "easy_apply": easy_apply,
            }
        except Exception as e:
            logger.debug(f"[LinkedIn] card error: {e}")
            return None

    async def _card_text(self, card, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                el = card.locator(sel).first
                text = await el.inner_text()
                if text.strip():
                    return text.strip()
            except Exception:
                pass
        return ""

    async def _get_description(self) -> str:
        for sel in [
            ".jobs-description__content",
            ".jobs-box__html-content",
            ".job-details-module",
            "#job-details",
        ]:
            try:
                el = self.page.locator(sel).first
                text = await el.inner_text()
                if len(text.strip()) > 100:
                    return text.strip()
            except Exception:
                pass
        return ""

    async def _has_easy_apply(self) -> bool:
        try:
            btns = await self.page.locator(
                "button.jobs-apply-button, button[aria-label*='Easy Apply']"
            ).all()
            for b in btns:
                label = (await b.inner_text() + " " + (await b.get_attribute("aria-label") or "")).lower()
                if "easy apply" in label and await b.is_visible():
                    return True
        except Exception:
            pass
        return False

    async def apply_to_job(self, job: dict) -> str:
        title = job.get("title", "?")
        company = job.get("company", "?")
        url = job.get("url", "")
        apply_channel = job.get("apply_channel") or (
            "easy_apply" if job.get("easy_apply") else "external"
        )

        logger.info(f"[LinkedIn] Applying ({apply_channel}): {title} @ {company}")
        try:
            if url and url not in self.page.url:
                await self.page.goto(url)
                await self.human_delay(2.5, 4)

            # V1: external-redirect path — "Apply on company website"
            if apply_channel == "external":
                return await self._apply_external(job)

            if not await self._click_easy_apply():
                logger.warning(f"[LinkedIn] No Easy Apply btn: {title}")
                return "skipped"

            if not await self._modal_open():
                logger.warning(f"[LinkedIn] Modal didn't open: {title}")
                return "failed"

            for step in range(10):
                await self._fill_page()
                action, btn = await self._get_action_btn()
                logger.debug(f"[LinkedIn] step={step + 1} action={action}")
                if action == "submit":
                    await btn.click()
                    await self.human_delay(2, 4)
                    logger.info(f"[LinkedIn] ✅ SUBMITTED: {title} @ {company}")
                    await self._dismiss()
                    return "applied"
                elif action in ("next", "review"):
                    await btn.click()
                    await self.human_delay(1.5, 3)
                else:
                    break

            logger.warning(f"[LinkedIn] No submit reached: {title}")
            await self._dismiss()
            return "failed"
        except Exception as e:
            logger.error(f"[LinkedIn] Exception: {title} — {e}")
            await self._dismiss()
            return "failed"

    async def _apply_external(self, job: dict) -> str:
        """Follow LinkedIn's "Apply on company website" link off-board, then
        run the UniversalFormFiller on whatever page loads (custom careers
        page, Workday, Greenhouse, Ashby, Lever, iCIMS, etc.).
        """
        from .universal_filler import UniversalFormFiller
        title = job.get("title", "?")

        # If we already captured the redirect target at discovery time, jump
        # straight to it; otherwise click the LinkedIn external-apply button
        # and follow whatever popup/new-tab opens.
        target = job.get("external_apply_url")
        target_page = self.page

        if target:
            await self.page.goto(target, wait_until="domcontentloaded", timeout=30000)
            await self.human_delay(2, 3.5)
        else:
            # Find the "Apply" button (LinkedIn renders it as the same
            # `.jobs-apply-button` selector but the label is "Apply" not
            # "Easy Apply" for off-board jobs).
            ctx = self._context
            popup_promise = ctx.wait_for_event("page", timeout=10000) if ctx else None
            clicked = False
            for sel in [
                "button.jobs-apply-button",
                ".jobs-apply-button--top-card button",
            ]:
                try:
                    btns = await self.page.locator(sel).all()
                    for b in btns:
                        label = (
                            await b.inner_text() + " " + (await b.get_attribute("aria-label") or "")
                        ).lower()
                        if "easy apply" in label:
                            continue  # this method only handles external
                        if not await b.is_visible():
                            continue
                        await b.scroll_into_view_if_needed()
                        await b.click()
                        clicked = True
                        break
                    if clicked:
                        break
                except Exception:
                    continue
            if not clicked:
                logger.warning(f"[LinkedIn] No external Apply button found: {title}")
                return "skipped"

            # LinkedIn opens the employer page in a new tab — switch to it.
            try:
                if popup_promise:
                    new_page = await popup_promise
                    if new_page:
                        target_page = new_page
                        await new_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception as e:
                logger.debug(f"[LinkedIn] external popup wait: {e}")
            await self.human_delay(2, 3.5)

        # Run the universal filler on whatever loaded.
        uff = UniversalFormFiller(target_page, self.profile)
        result = await uff.run()
        logger.info(
            f"[LinkedIn-external] {title} — pages={result.pages_filled} "
            f"filled={result.fields_filled} reached_review={result.reached_review} "
            f"reason={result.reason!r}"
        )

        # Wait briefly for user-driven submit (URL/banner heuristic).
        success_signals = [
            "text=/thank you for applying/i",
            "text=/application submitted/i",
            "text=/we[' ]?ve received your application/i",
            "text=/successfully\\s+applied/i",
        ]
        try:
            start_url = target_page.url
            elapsed = 0.0
            while elapsed < 120:
                for sig in success_signals:
                    try:
                        if await target_page.locator(sig).first.is_visible(timeout=200):
                            return "applied"
                    except Exception:
                        pass
                cur = target_page.url
                if cur != start_url and any(seg in cur.lower() for seg in
                                            ("thank", "success", "confirm", "complete")):
                    return "applied"
                import asyncio as _a
                await _a.sleep(1.5)
                elapsed += 1.5
        except Exception as e:
            logger.debug(f"[LinkedIn-external] success-wait error: {e}")

        return "skipped" if result.reached_review else "failed"

    async def _click_easy_apply(self) -> bool:
        for sel in [
            "button.jobs-apply-button",
            "button[aria-label*='Easy Apply']",
            ".jobs-apply-button--top-card button",
            ".jobs-s-apply button",
        ]:
            try:
                btns = await self.page.locator(sel).all()
                for b in btns:
                    label = (
                        await b.inner_text() + " " + (await b.get_attribute("aria-label") or "")
                    ).lower()
                    if "easy apply" in label and await b.is_visible():
                        await b.scroll_into_view_if_needed()
                        await self.human_delay(0.3, 0.6)
                        await b.click()
                        await self.human_delay(2, 3.5)
                        return True
            except Exception:
                continue
        return False

    async def _modal_open(self) -> bool:
        try:
            modal = self.page.locator(
                ".jobs-easy-apply-modal, .artdeco-modal[role='dialog']"
            ).first
            return await modal.is_visible()
        except Exception:
            return False

    async def _fill_page(self):
        await self.human_delay(1, 2)
        await self._fill_inputs()
        await self._fill_textarea()
        await self._handle_radios()
        await self._handle_selects()
        await self._upload_resume()
        await self.human_delay(0.5, 1)

    async def _fill_inputs(self):
        p = self.profile
        profile_map = {
            "phone": p.get("phone", ""),
            "mobile": p.get("phone", ""),
            "first name": p.get("full_name", "").split()[0] if p.get("full_name") else "",
            "last name": p.get("full_name", "").split()[-1] if p.get("full_name") else "",
            "email": p.get("email", ""),
            "city": p.get("city", ""),
            "location": p.get("city", ""),
            "years": str(p.get("years_of_experience", "")),
            "experience": str(p.get("years_of_experience", "")),
            "salary": p.get("expected_salary", ""),
            "ctc": p.get("expected_salary", ""),
            "linkedin": "linkedin.com/in/raghu-ram-vellanki-95134b248",
            "portfolio": p.get("portfolio_url", ""),
            "website": p.get("portfolio_url", ""),
            "notice": p.get("notice_period", "Immediate"),
        }
        try:
            labels = await self.page.locator(
                ".jobs-easy-apply-form-section__grouping label, .fb-form-element label"
            ).all()
            for lbl in labels:
                lt = (await lbl.inner_text()).lower().strip()
                fid = await lbl.get_attribute("for")
                try:
                    inp = self.page.locator(f"#{fid}").first if fid else \
                          lbl.locator("xpath=following-sibling::input").first
                    if not await inp.is_visible():
                        continue
                    val = await inp.input_value()
                    if val.strip():
                        continue
                    for key, fill_val in profile_map.items():
                        if key in lt and fill_val:
                            for ch in str(fill_val):
                                await inp.type(ch, delay=random.randint(40, 120))
                            await self.human_delay(0.2, 0.5)
                            break
                    else:
                        if await inp.get_attribute("type") == "number":
                            yoe = str(p.get("years_of_experience", "1"))
                            await inp.fill(yoe)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"_fill_inputs: {e}")

    async def _fill_textarea(self):
        cover = self.profile.get("cover_letter_template", "")
        if not cover:
            return
        try:
            for ta in await self.page.locator("textarea").all():
                if await ta.is_visible():
                    val = await ta.input_value()
                    if not val.strip():
                        for ch in cover:
                            await ta.type(ch, delay=random.randint(30, 80))
                        await self.human_delay(0.3, 0.7)
                        break
        except Exception as e:
            logger.debug(f"_fill_textarea: {e}")

    async def _handle_radios(self):
        try:
            for fs in await self.page.locator("fieldset").all():
                radios = await fs.locator("input[type='radio']").all()
                if not radios:
                    continue
                any_selected = any([await r.is_checked() for r in radios])
                if any_selected:
                    continue
                clicked = False
                for r in radios:
                    rid = await r.get_attribute("id") or ""
                    try:
                        lbl_text = (await self.page.locator(f"label[for='{rid}']").inner_text()).lower()
                        if "yes" in lbl_text:
                            await r.click()
                            await self.human_delay(0.2, 0.5)
                            clicked = True
                            break
                    except Exception:
                        pass
                if not clicked and radios:
                    await radios[0].click()
                    await self.human_delay(0.2, 0.5)
        except Exception as e:
            logger.debug(f"_handle_radios: {e}")

    async def _handle_selects(self):
        pref = ["yes", "bachelor", "b.tech", "english", "india", "full-time", "immediate"]
        try:
            for sel_el in await self.page.locator("select").all():
                if not await sel_el.is_visible():
                    continue
                opts = await sel_el.locator("option").all()
                if not opts:
                    continue
                cur = (await sel_el.input_value()).lower().strip()
                if cur not in ["", "select an option", "please select", "choose"]:
                    continue
                picked = False
                for opt in opts[1:]:
                    opt_text = (await opt.inner_text()).lower()
                    if any(p in opt_text for p in pref):
                        val = await opt.get_attribute("value") or ""
                        await sel_el.select_option(value=val)
                        await self.human_delay(0.2, 0.5)
                        picked = True
                        break
                if not picked and len(opts) > 1:
                    val = await opts[1].get_attribute("value") or ""
                    await sel_el.select_option(value=val)
                    await self.human_delay(0.2, 0.5)
        except Exception as e:
            logger.debug(f"_handle_selects: {e}")

    async def _upload_resume(self):
        resume_path = self.profile.get("resume_path", "")
        if not resume_path:
            return
        # Make absolute relative to project root
        if not os.path.isabs(resume_path):
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            resume_path = os.path.join(root, resume_path)
        if not os.path.exists(resume_path):
            return
        try:
            for fi in await self.page.locator("input[type='file']").all():
                try:
                    await fi.set_input_files(resume_path)
                    await self.page.wait_for_timeout(2000)
                    return
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"_upload_resume: {e}")

    async def _get_action_btn(self) -> tuple[str | None, object | None]:
        try:
            footer = self.page.locator(
                ".jobs-easy-apply-modal footer, .artdeco-modal footer"
            ).first
            btns = await footer.locator("button").all()
            for b in reversed(btns):
                if not await b.is_visible():
                    continue
                t = (await b.inner_text()).lower().strip()
                if "submit" in t:
                    return "submit", b
                if "review" in t:
                    return "review", b
                if "next" in t or "continue" in t:
                    return "next", b
        except Exception:
            pass
        try:
            for b in reversed(await self.page.locator("button.artdeco-button--primary").all()):
                if not await b.is_visible():
                    continue
                t = (await b.inner_text()).lower().strip()
                if "submit" in t:
                    return "submit", b
                if "review" in t:
                    return "review", b
                if "next" in t:
                    return "next", b
        except Exception:
            pass
        return None, None

    async def _dismiss(self):
        for sel in ["button[aria-label='Dismiss']", ".artdeco-modal__dismiss"]:
            try:
                b = self.page.locator(sel).first
                if await b.is_visible():
                    await b.click()
                    await self.page.wait_for_timeout(1000)
                    return
            except Exception:
                pass
