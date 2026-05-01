"""
Naukri Agent — scrapes Naukri.com for jobs.
Uses public search (no login needed for discovery).
"""
import asyncio
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
    # Naukri's anti-bot serves a blank splash to headless Chromium.
    # Visible window + stealth init script (in BaseAgent) are required.
    requires_visible_browser = True

    async def login(self) -> bool:
        # Discovery works on anonymous search URLs, so we always return True.
        # If credentials are present we attempt a best-effort login (used later
        # by apply_to_job), but a failure here must NOT skip the platform.
        email = self.credentials.get("email", "")
        password = self.credentials.get("password", "")
        if not email or not password:
            logger.info("[Naukri] No credentials — discovery only, no login attempted")
            return True

        try:
            await self.page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            await self.human_delay(2, 4)
            email_selectors = [
                "input#usernameField",
                "input[name='email']",
                "input[placeholder*='Email' i]",
                "input[placeholder*='Username' i]",
                "input[type='email']",
            ]
            filled_email = False
            for sel in email_selectors:
                try:
                    await self.page.fill(sel, email, timeout=3000)
                    filled_email = True
                    break
                except Exception:
                    continue
            if not filled_email:
                logger.warning("[Naukri] Could not find email field — continuing without login")
                return True
            await self.human_delay(0.5, 1)
            try:
                await self.page.fill("input#passwordField, input[type='password']", password, timeout=3000)
            except Exception:
                logger.warning("[Naukri] Could not find password field — continuing without login")
                return True
            await self.human_delay(0.5, 1)
            await self.page.keyboard.press("Enter")
            await self.human_delay(3, 5)
            logger.info("[Naukri] Login attempted (discovery proceeds either way)")
        except Exception as e:
            logger.warning(f"[Naukri] Login attempt errored ({e}) — continuing for discovery")
        return True

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
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    # Naukri is a Next.js SPA — the splash screen renders first,
                    # then job cards hydrate. Wait for an actual job link before
                    # scraping. data-job-id is the stable attribute.
                    try:
                        await self.page.wait_for_selector(
                            "a[href*='/job-listings-'], [data-job-id]",
                            timeout=20000,
                        )
                    except Exception:
                        logger.warning(f"[Naukri] No cards rendered on '{keyword}' page {page_num}")
                        break
                    await self.human_delay(1, 2)
                except Exception as e:
                    logger.warning(f"[Naukri] page load error: {e}")
                    break

                cards = await self.page.locator("[data-job-id]").all()
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
                    await self.human_delay(0.3, 0.6)

        return jobs

    async def _parse_card(self, card) -> dict | None:
        try:
            job_id = await card.get_attribute("data-job-id")

            # The job link is the most stable element: <a href="/job-listings-...">
            url = ""
            title = ""
            try:
                link = card.locator("a[href*='/job-listings-']").first
                href = await link.get_attribute("href")
                if href:
                    url = href if href.startswith("http") else BASE_URL + href
                title = (await link.inner_text()).strip()
            except Exception:
                pass

            # Company — try class-based first, then fall back to common patterns
            company = ""
            for sel in ["a.comp-name", ".comp-name", ".companyInfo a", ".subTitle"]:
                try:
                    company = (await card.locator(sel).first.inner_text()).strip()
                    if company:
                        break
                except Exception:
                    continue

            # Location
            location = ""
            for sel in [".locWdth", ".loc-wrap span", "span.locWdth", ".loc"]:
                try:
                    location = (await card.locator(sel).first.inner_text()).strip()
                    if location:
                        break
                except Exception:
                    continue

            # Experience (e.g. "4-6 Yrs")
            experience = ""
            for sel in [".expwdth", ".exp", ".exp-wrap span"]:
                try:
                    experience = (await card.locator(sel).first.inner_text()).strip()
                    if experience:
                        break
                except Exception:
                    continue

            # Brief description preview (helps the scorer when no full JD is fetched)
            description = ""
            for sel in [".job-desc", ".job-description"]:
                try:
                    description = (await card.locator(sel).first.inner_text()).strip()
                    if description:
                        break
                except Exception:
                    continue

            if not title:
                return None

            if not job_id and url:
                m = re.search(r"-(\d+)(?:\?|$)", url)
                if m:
                    job_id = m.group(1)
            if not job_id:
                import hashlib
                job_id = "naukri_" + hashlib.md5(
                    title.encode() + (company or "").encode()
                ).hexdigest()[:12]
            elif not str(job_id).startswith("naukri_"):
                job_id = f"naukri_{job_id}"

            return {
                "job_id": job_id,
                "platform": "naukri",
                "title": title,
                "company": company or "Unknown",
                "location": location or "",
                "experience": experience,
                "url": url,
                "description": description,
                "easy_apply": True,
            }
        except Exception as e:
            logger.debug(f"[Naukri] parse_card error: {e}")
            return None

    async def get_description(self, url: str) -> str:
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait for the SPA to hydrate the JD section.
            try:
                await self.page.wait_for_selector(
                    'section[class*="job-desc-container"], div[class*="JDC__dang-inner-html"]',
                    timeout=15000,
                )
            except Exception:
                pass
            await self.human_delay(0.5, 1)
            # Naukri uses CSS modules with hashed class names; match by stable prefix.
            for sel in [
                'div[class*="JDC__dang-inner-html"]',
                'section[class*="job-desc-container"]',
                'div[class*="styles_short-desc"]',
                'div[class*="job-desc"]',
            ]:
                try:
                    text = await self.page.locator(sel).first.inner_text()
                    if len(text.strip()) > 100:
                        return text.strip()
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Naukri] get_description error: {e}")
        return ""

    async def apply_to_job(self, job: dict) -> str:
        """Open the Naukri job page, click Apply, auto-fill the form, then
        wait for the user to review and click the final submit themselves.

        Returns:
          "applied" — apply form was reached + filled. Final submit was
                      either pressed by the user or the page indicated success.
          "skipped" — only the login-prompt button was visible (no creds saved)
                      or the user didn't submit within the wait window.
          "failed"  — page didn't load or no apply button rendered.
        """
        title = job.get("title", "?")
        url = job.get("url", "")
        if not url:
            return "skipped"
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await self.page.wait_for_selector(
                    "#apply-button, #login-apply-button, #reg-apply-button",
                    timeout=15000,
                )
            except Exception:
                logger.warning(f"[Naukri] No apply button rendered for: {title}")
                return "failed"
            await self.human_delay(0.8, 1.5)

            # If only the login-prompt buttons are visible, we have no session.
            real_apply = await self.page.locator("button#apply-button, a#apply-button").count()
            if not real_apply:
                login_btn = await self.page.locator("#login-apply-button, #reg-apply-button").count()
                if login_btn:
                    logger.info(f"[Naukri] Apply needs login (skipping): {title}")
                    return "skipped"
                return "failed"

            if not await self.safe_click("button#apply-button, a#apply-button", timeout=4000):
                return "failed"
            logger.info(f"[Naukri] Apply clicked, waiting for form: {title}")
            await self.human_delay(1.5, 3)

            # Auto-fill the chatbot/questionnaire as it progressively reveals
            # questions. Naukri uses a left-side chatbot panel for most apply
            # flows; questions appear one at a time as you answer.
            await self._fill_naukri_form()

            _log_msg = (
                f"[Naukri] Form auto-filled. Review and click final Submit "
                f"in the browser (waiting up to 120s): {title}"
            )
            logger.info(_log_msg)

            # Wait for the user to manually click the final submit. We detect
            # success by any of:
            #   - URL changes away from the job-listings page
            #   - A "successfully applied" / "Application submitted" indicator
            #   - The Apply button disappears (page advanced)
            success_signals = [
                "text=/successfully\\s+applied/i",
                "text=/application\\s+submitted/i",
                "text=/you have applied/i",
                "text=/already applied/i",
            ]
            try:
                # Wait up to 120s for either a success indicator or URL change.
                start_url = self.page.url
                deadline = 120.0
                step = 1.5
                elapsed = 0.0
                while elapsed < deadline:
                    # Any success indicator visible?
                    for sig in success_signals:
                        try:
                            if await self.page.locator(sig).first.is_visible(timeout=200):
                                logger.info(f"[Naukri] Submission detected for: {title}")
                                return "applied"
                        except Exception:
                            pass
                    # URL changed → likely submitted/redirected
                    if self.page.url != start_url and "/job-listings-" not in self.page.url:
                        logger.info(f"[Naukri] Page navigated after submit: {title}")
                        return "applied"
                    await asyncio.sleep(step)
                    elapsed += step
                logger.info(f"[Naukri] No submit detected within 120s, moving on: {title}")
                return "skipped"
            except Exception as e:
                logger.warning(f"[Naukri] post-fill wait error: {e}")
                return "applied"
        except Exception as e:
            logger.error(f"[Naukri] apply error: {e}")
            return "failed"

    # ── Form auto-fill helpers ───────────────────────────────────────────

    async def _fill_naukri_form(self):
        """Naukri's apply UX is a chatbot panel that reveals one question
        at a time. Run multiple passes — fill what's visible, wait for the
        next question to appear, fill again, etc. Stops when no new fields
        appear in a pass or after a sane upper bound.
        """
        p = self.profile
        first_name = (p.get("full_name") or "").split()[0] if p.get("full_name") else ""
        last_name = (p.get("full_name") or "").split()[-1] if p.get("full_name") else ""
        profile_map = {
            "first name": first_name,
            "last name": last_name,
            "full name": p.get("full_name", ""),
            "name": p.get("full_name", ""),
            "phone": p.get("phone", ""),
            "mobile": p.get("phone", ""),
            "contact": p.get("phone", ""),
            "email": p.get("email", ""),
            "city": p.get("city", ""),
            "current location": p.get("city", ""),
            "location": p.get("city", ""),
            "current title": p.get("current_title", ""),
            "designation": p.get("current_title", ""),
            "role": p.get("current_title", ""),
            "current company": p.get("current_company", ""),
            "company": p.get("current_company", ""),
            "experience": str(p.get("years_of_experience", "")),
            "years": str(p.get("years_of_experience", "")),
            "notice": p.get("notice_period", "Immediate"),
            "expected salary": str(p.get("expected_salary", "")),
            "expected ctc": str(p.get("expected_salary", "")),
            "current ctc": str(p.get("current_salary", p.get("expected_salary", ""))),
            "ctc": str(p.get("expected_salary", "")),
            "linkedin": p.get("linkedin_url", ""),
            "portfolio": p.get("portfolio_url", ""),
            "website": p.get("portfolio_url", ""),
        }

        max_passes = 8
        for pass_num in range(max_passes):
            filled_this_pass = 0
            filled_this_pass += await self._fill_visible_inputs(profile_map)
            filled_this_pass += await self._fill_visible_selects()
            filled_this_pass += await self._fill_visible_radios()
            # If the chatbot has a Next/Continue/Send button after each answer,
            # click it so the next question reveals.
            advanced = await self._click_next_in_form()
            if filled_this_pass == 0 and not advanced:
                break
            await self.human_delay(0.6, 1.2)
        logger.info(f"[Naukri] form auto-fill done after {pass_num + 1} pass(es)")

    async def _fill_visible_inputs(self, profile_map: dict) -> int:
        """Fill every visible, empty <input>/<textarea> we can map by its
        label, placeholder, name, or id."""
        filled = 0
        try:
            inputs = await self.page.locator(
                "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='checkbox']):not([type='radio']):not([type='file']), textarea"
            ).all()
            for inp in inputs:
                try:
                    if not await inp.is_visible():
                        continue
                    if await inp.is_disabled():
                        continue
                    val = (await inp.input_value()).strip()
                    if val:
                        continue

                    hint = await self._field_hint(inp)
                    fill_val = self._lookup_value(hint, profile_map)
                    if not fill_val:
                        continue

                    await inp.click()
                    await inp.fill(str(fill_val))
                    await self.human_delay(0.2, 0.5)
                    filled += 1
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Naukri] _fill_visible_inputs: {e}")
        return filled

    async def _fill_visible_selects(self) -> int:
        """Pick a sensible option for any unset visible <select>."""
        prefs = ["yes", "immediate", "less than 15 days", "15 days", "1 month",
                 "bachelor", "b.tech", "english", "india", "full-time", "permanent"]
        filled = 0
        try:
            for sel_el in await self.page.locator("select").all():
                try:
                    if not await sel_el.is_visible():
                        continue
                    cur = (await sel_el.input_value() or "").lower().strip()
                    if cur and cur not in ("", "select", "select an option", "please select", "choose"):
                        continue
                    opts = await sel_el.locator("option").all()
                    if len(opts) < 2:
                        continue
                    chosen = None
                    for opt in opts[1:]:
                        txt = (await opt.inner_text()).lower()
                        if any(p in txt for p in prefs):
                            chosen = opt
                            break
                    if chosen is None:
                        chosen = opts[1]
                    val = await chosen.get_attribute("value") or ""
                    await sel_el.select_option(value=val)
                    await self.human_delay(0.2, 0.5)
                    filled += 1
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Naukri] _fill_visible_selects: {e}")
        return filled

    async def _fill_visible_radios(self) -> int:
        """For each unselected radio group, prefer 'Yes' / first option."""
        filled = 0
        try:
            for fs in await self.page.locator("fieldset, [role='radiogroup']").all():
                try:
                    radios = await fs.locator("input[type='radio']").all()
                    if not radios:
                        continue
                    if any([await r.is_checked() for r in radios]):
                        continue
                    picked = False
                    for r in radios:
                        rid = await r.get_attribute("id") or ""
                        if rid:
                            try:
                                lbl = (await self.page.locator(f"label[for='{rid}']").first.inner_text()).lower()
                                if "yes" in lbl:
                                    await r.click()
                                    picked = True
                                    break
                            except Exception:
                                pass
                    if not picked:
                        try:
                            await radios[0].click()
                            picked = True
                        except Exception:
                            pass
                    if picked:
                        filled += 1
                        await self.human_delay(0.2, 0.5)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[Naukri] _fill_visible_radios: {e}")
        return filled

    async def _click_next_in_form(self) -> bool:
        """Naukri's chatbot expects you to confirm each answer with a Next/
        Save/Send button before the next question reveals. Click it if found.
        We deliberately avoid clicking the *final* Submit/Apply button so the
        user can review."""
        chat_button_selectors = [
            "button:has-text('Save and Continue')",
            "button:has-text('Save & Continue')",
            "button:has-text('Continue')",
            "button:has-text('Next')",
            "button:has-text('Send')",
            "div[role='button']:has-text('Send')",
        ]
        for sel in chat_button_selectors:
            try:
                btn = self.page.locator(sel).first
                if await btn.is_visible(timeout=300):
                    txt = (await btn.inner_text()).strip().lower()
                    # Refuse to press a button that looks like the final submit
                    if any(t in txt for t in ("submit", "apply now", "confirm apply", "finish")):
                        continue
                    await btn.click()
                    await self.human_delay(0.4, 0.8)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _lookup_value(hint: str, profile_map: dict) -> str:
        if not hint:
            return ""
        h = hint.lower()
        # Longest-key-first so "expected ctc" beats "ctc"
        for key in sorted(profile_map.keys(), key=len, reverse=True):
            if key in h and profile_map[key]:
                return str(profile_map[key])
        return ""

    @staticmethod
    async def _field_hint(inp) -> str:
        """Combine label/placeholder/name/id/aria-label into one string the
        caller can match against profile_map keys."""
        bits = []
        for attr in ("placeholder", "name", "id", "aria-label", "title"):
            try:
                v = await inp.get_attribute(attr)
                if v:
                    bits.append(v)
            except Exception:
                pass
        # Look up an associated <label for=id>
        try:
            fid = await inp.get_attribute("id")
            if fid:
                lbl = inp.page.locator(f"label[for='{fid}']").first
                if await lbl.count() > 0:
                    bits.append(await lbl.inner_text())
        except Exception:
            pass
        # Or a label that wraps the input
        try:
            parent_lbl = inp.locator("xpath=ancestor::label[1]")
            if await parent_lbl.count() > 0:
                bits.append(await parent_lbl.first.inner_text())
        except Exception:
            pass
        return " ".join(bits)
