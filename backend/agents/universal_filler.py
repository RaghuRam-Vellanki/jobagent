"""
UniversalFormFiller — V1 apply-engine core.

One Playwright form-filler that runs against ANY page: LinkedIn Easy Apply
modals, Naukri Quick Apply forms, Workday tenants, Greenhouse/Ashby/Lever
direct URLs, custom company careers pages (Boat Lifestyle, etc.).

Per-platform wrappers (linkedin_agent, naukri_agent, ATS) only handle entry
quirks (clicking "Apply Manually" on Workday, dismissing LinkedIn save-modal,
etc.) and then call `UniversalFormFiller(page, profile).run()`.

Contract:
- Fills inputs / selects / radios / checkboxes / file uploads using a synonym
  table that maps profile attributes to label/aria-label/placeholder text.
- Multi-pass (≤5) progressive disclosure: clicks Next/Continue between passes
  to handle multi-page forms (Workday, Greenhouse with custom questions).
- NEVER clicks final-submission buttons (Submit / Apply Now / Confirm).
- Returns a FillResult with {pages_filled, fields_filled, fields_skipped,
  reason, reached_review}.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page, ElementHandle, Locator, TimeoutError as PWTimeout

logger = logging.getLogger("agent.universal_filler")


# ─── Synonym table: profile attribute → list of label substrings ────────
# Keys map to canonical profile fields. Matching is case-insensitive
# substring against label / aria-label / placeholder / name / id text.
SYNONYMS: dict[str, list[str]] = {
    "first_name": ["first name", "given name", "firstname", "fname"],
    "last_name": ["last name", "surname", "family name", "lastname", "lname"],
    "full_name": ["full name", "your name", "applicant name", "candidate name", "name"],
    "email": ["email", "e-mail", "email address", "work email"],
    "phone": ["phone", "mobile", "contact number", "mobile no", "contact no", "telephone"],
    "linkedin_url": ["linkedin", "linkedin profile", "linkedin url"],
    "portfolio_url": ["portfolio", "personal website", "personal site", "github", "website"],
    "current_company": ["current company", "current employer", "employer", "company"],
    "current_title": ["current role", "current title", "designation", "current job", "job title"],
    "years_of_experience": [
        "total experience", "years of experience", "yoe", "work exp",
        "years of work experience", "experience (years)", "total years",
    ],
    "current_ctc": ["current ctc", "current salary", "current compensation"],
    "expected_ctc": ["expected ctc", "expected salary", "salary expectation", "expected compensation"],
    "notice_period": ["notice period", "availability", "when can you start", "earliest start"],
    "city": ["current city", "location", "city", "place", "current location"],
    "state": ["state", "province"],
    "country": ["country"],
    "gender": ["gender"],
    "resume_file": ["resume", "cv", "upload resume", "attach resume", "upload cv"],
    "cover_letter_text": ["cover letter", "additional information", "why this role", "tell us"],
    "hear_about_us": ["how did you hear", "source", "referral source", "how did you find"],
    "work_auth": ["authorized to work", "work authorization", "visa", "right to work"],
    "willing_to_relocate": ["willing to relocate", "relocate"],
    "graduation_year": ["graduation year", "year of graduation", "passing year", "year of passing"],
}

# Buttons we will click to advance multi-page forms.
NAV_BUTTON_PATTERNS = [
    r"^next$", r"^continue$", r"^save and continue$", r"^save & continue$",
    r"^next step$", r"^proceed$", r"^review$",
]

# Buttons we MUST NEVER click (final submission).
SUBMIT_BLACKLIST = [
    r"^submit$", r"submit application", r"^apply now$", r"^confirm$",
    r"confirm submission", r"^send application$", r"^complete application$",
]

MAX_PASSES = 5
PER_PASS_TIMEOUT_MS = 8000


@dataclass
class FillResult:
    pages_filled: int = 0
    fields_filled: int = 0
    fields_skipped: list[str] = field(default_factory=list)
    reason: str = ""
    reached_review: bool = False


class UniversalFormFiller:
    """Generic Playwright form filler. See module docstring."""

    def __init__(self, page: Page, profile: dict, *, max_passes: int = MAX_PASSES):
        self.page = page
        self.profile = self._normalize_profile(profile)
        self.max_passes = max_passes
        self.result = FillResult()

    # ─── Public entry point ────────────────────────────────────────────

    async def run(self) -> FillResult:
        """Fill the current page (and any progressive-disclosure pages that
        follow) until we reach a Submit-only state or hit max_passes."""
        # Per-platform entry shims (small, ≤30 LOC each). Today: Workday only.
        try:
            from . import _workday_preflow
            await _workday_preflow.run(self.page)
        except Exception as e:
            logger.debug(f"workday preflow error: {e}")

        for pass_idx in range(1, self.max_passes + 1):
            logger.info(f"[universal-filler] pass {pass_idx}/{self.max_passes}")
            try:
                await self._wait_for_form_ready()
            except Exception as e:
                logger.debug(f"form-ready wait failed: {e}")

            if await self._has_captcha():
                self.result.reason = "captcha — please solve manually"
                logger.warning(self.result.reason)
                return self.result

            filled_this_pass = await self._fill_visible_fields()
            self.result.fields_filled += filled_this_pass
            self.result.pages_filled = pass_idx

            advanced = await self._click_nav_button()
            if not advanced:
                # No Next/Continue visible — we are at the review/submit page.
                self.result.reached_review = True
                self.result.reason = "reached review page; awaiting user submit"
                logger.info(self.result.reason)
                return self.result

            # Brief settle for the next page to render.
            await asyncio.sleep(1.2)

        self.result.reason = "max passes reached without finding submit page"
        logger.warning(self.result.reason)
        return self.result

    # ─── Profile normalization ─────────────────────────────────────────

    @staticmethod
    def _normalize_profile(p: dict) -> dict[str, str]:
        """Flatten profile into a synonym-key → string-value map."""
        full_name = (p.get("full_name") or "").strip()
        first = (p.get("first_name") or full_name.split(" ")[0] if full_name else "").strip()
        last = (p.get("last_name") or
                (" ".join(full_name.split(" ")[1:]) if full_name and " " in full_name else "")).strip()

        return {
            "first_name": first,
            "last_name": last,
            "full_name": full_name or f"{first} {last}".strip(),
            "email": str(p.get("email") or ""),
            "phone": str(p.get("phone") or ""),
            "linkedin_url": str(p.get("linkedin_url") or p.get("portfolio_url") or ""),
            "portfolio_url": str(p.get("portfolio_url") or ""),
            "current_company": str(p.get("current_company") or ""),
            "current_title": str(p.get("current_title") or ""),
            "years_of_experience": str(p.get("years_of_experience") or 0),
            "current_ctc": str(p.get("current_ctc") or ""),
            "expected_ctc": str(p.get("expected_salary") or p.get("expected_ctc") or ""),
            "notice_period": str(p.get("notice_period") or "Immediate"),
            "city": str(p.get("city") or ""),
            "state": str(p.get("state") or ""),
            "country": str(p.get("country") or "India"),
            "gender": str(p.get("gender") or ""),
            "resume_file": str(p.get("resume_path") or ""),
            "cover_letter_text": str(p.get("cover_letter_template") or ""),
            "hear_about_us": "LinkedIn",
            "work_auth": "Yes",  # Indian users applying to Indian jobs
            "willing_to_relocate": "Yes",
            "graduation_year": str(p.get("graduation_year") or ""),
        }

    # ─── Waits / captcha ───────────────────────────────────────────────

    async def _wait_for_form_ready(self):
        """Wait for any input/select/textarea to be present, with a short cap."""
        try:
            await self.page.wait_for_selector(
                "input, select, textarea", timeout=PER_PASS_TIMEOUT_MS, state="visible"
            )
        except PWTimeout:
            return  # No form fields visible — likely an intermediate review page.

    async def _has_captcha(self) -> bool:
        try:
            iframes = self.page.locator(
                "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[title*='captcha' i]"
            )
            return await iframes.count() > 0
        except Exception:
            return False

    # ─── Field discovery + filling ─────────────────────────────────────

    async def _fill_visible_fields(self) -> int:
        """Walk every visible input/select/textarea and try to fill it."""
        filled = 0
        # We snapshot handles up-front because filling can cause DOM mutations.
        try:
            handles = await self.page.query_selector_all(
                "input:not([type=hidden]):not([type=submit]):not([type=button]),"
                " select, textarea"
            )
        except Exception as e:
            logger.debug(f"query_selector_all failed: {e}")
            return 0

        for handle in handles:
            try:
                if not await handle.is_visible():
                    continue
                if await handle.is_disabled():
                    continue
            except Exception:
                continue

            label_text = await self._field_label(handle)
            if not label_text:
                continue

            attr = self._match_synonym(label_text)
            if not attr:
                self.result.fields_skipped.append(label_text[:80])
                continue

            value = self.profile.get(attr, "")
            if not value:
                continue

            ok = await self._fill_one(handle, attr, value)
            if ok:
                filled += 1

        return filled

    async def _field_label(self, handle: ElementHandle) -> str:
        """Best-effort label resolution: aria-label → label[for] → placeholder
        → name → id → nearby text."""
        try:
            for attr in ("aria-label", "placeholder", "name", "id"):
                v = await handle.get_attribute(attr)
                if v:
                    return v.strip()
            # <label for="X">…</label>
            id_ = await handle.get_attribute("id")
            if id_:
                lbl = await self.page.query_selector(f"label[for='{id_}']")
                if lbl:
                    return (await lbl.inner_text()).strip()
            # Parent label (for type=radio / checkbox commonly)
            parent = await handle.evaluate_handle("el => el.closest('label')")
            if parent:
                el = parent.as_element()
                if el:
                    txt = (await el.inner_text()).strip()
                    if txt:
                        return txt
        except Exception:
            pass
        return ""

    @staticmethod
    def _match_synonym(label: str) -> str | None:
        low = label.lower()
        for attr, synonyms in SYNONYMS.items():
            for syn in synonyms:
                if syn in low:
                    return attr
        return None

    async def _fill_one(self, handle: ElementHandle, attr: str, value: str) -> bool:
        try:
            tag = (await handle.evaluate("el => el.tagName")).lower()
            input_type = (await handle.get_attribute("type") or "").lower()

            if attr == "resume_file" and input_type == "file":
                return await self._upload_file(handle, value)

            if input_type in ("radio", "checkbox"):
                return await self._set_choice(handle, value)

            if tag == "select":
                return await self._select_option(handle, value)

            # default: text/textarea/email/tel/url/number
            await handle.scroll_into_view_if_needed()
            await handle.fill("")
            await handle.fill(value)
            return True
        except Exception as e:
            logger.debug(f"fill_one({attr}) failed: {e}")
            return False

    async def _upload_file(self, handle: ElementHandle, path: str) -> bool:
        if not path:
            return False
        try:
            await handle.set_input_files(path)
            return True
        except Exception as e:
            logger.debug(f"upload_file failed: {e}")
            return False

    async def _set_choice(self, handle: ElementHandle, value: str) -> bool:
        """For radio/checkbox: check if the value text matches its label."""
        try:
            label = await self._field_label(handle)
            if value.lower() in label.lower() or label.lower() in value.lower():
                await handle.check()
                return True
        except Exception as e:
            logger.debug(f"set_choice failed: {e}")
        return False

    async def _select_option(self, handle: ElementHandle, value: str) -> bool:
        """Try select-by-label (case-insensitive substring) for native <select>."""
        try:
            options = await handle.query_selector_all("option")
            for opt in options:
                txt = (await opt.inner_text()).strip()
                if value.lower() in txt.lower() or txt.lower() in value.lower():
                    val = await opt.get_attribute("value")
                    if val is not None:
                        await handle.select_option(value=val)
                        return True
            # Fallback: first non-empty option for required selects (Yes/No defaults)
            return False
        except Exception as e:
            logger.debug(f"select_option failed: {e}")
            return False

    # ─── Navigation buttons ────────────────────────────────────────────

    async def _click_nav_button(self) -> bool:
        """Find a Next/Continue button. NEVER click submit/apply-now buttons."""
        try:
            buttons: list[Locator] = []
            for tag in ("button", "input[type=button]", "input[type=submit]",
                        "[role=button]", "a"):
                buttons.append(self.page.locator(tag))

            # Iterate every candidate; pick the first visible one whose label
            # matches a NAV pattern and does NOT match a submit-blacklist pattern.
            seen_texts: list[str] = []
            for loc in buttons:
                count = await loc.count()
                for i in range(count):
                    el = loc.nth(i)
                    try:
                        if not await el.is_visible():
                            continue
                        text = (await el.inner_text() or "").strip()
                        if not text:
                            text = (await el.get_attribute("value") or "").strip()
                        if not text:
                            text = (await el.get_attribute("aria-label") or "").strip()
                        low = text.strip().lower()
                        if not low:
                            continue
                        seen_texts.append(low)

                        if any(re.search(p, low) for p in SUBMIT_BLACKLIST):
                            continue
                        if any(re.search(p, low) for p in NAV_BUTTON_PATTERNS):
                            await el.scroll_into_view_if_needed()
                            await el.click()
                            logger.info(f"[universal-filler] clicked nav button: {text!r}")
                            return True
                    except Exception:
                        continue

            logger.debug(f"no nav button found; visible buttons: {seen_texts[:12]}")
            return False
        except Exception as e:
            logger.debug(f"click_nav_button error: {e}")
            return False


# ─── Module-level convenience ────────────────────────────────────────────

async def fill_form(page: Page, profile: dict, max_passes: int = MAX_PASSES) -> FillResult:
    """Run the universal filler against `page` using `profile`. Returns FillResult."""
    return await UniversalFormFiller(page, profile, max_passes=max_passes).run()
