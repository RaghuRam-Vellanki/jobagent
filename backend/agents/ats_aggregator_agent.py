"""
ATS Aggregator — fetches jobs directly from Greenhouse + Ashby JSON APIs.

Why this exists: scraping aggregator UIs (LinkedIn/Indeed/Wellfound) is an
arms race against bot detection. But many top companies host their careers
on Greenhouse or Ashby, and those ATS providers expose public JSON APIs by
design (so search engines + their customers' marketing can index jobs).

We curate a list of companies and hit each ATS API. Discovery is pure HTTP —
no browser needed. Apply opens the job's URL in a Playwright window, fills
common form fields, then waits for the user to review + click submit.
"""
import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

from .base_agent import BaseAgent

logger = logging.getLogger("agent.ats")


# ── Curated company list ────────────────────────────────────────────────
# Each entry: {"slug": "<api-slug>", "ats": "greenhouse" | "ashby"}.
# Verified to return jobs from the public API as of 2026-04. If a company
# changes ATS or shuts a board, the agent logs a warning and keeps going.
COMPANIES: list[dict[str, str]] = [
    # ── Greenhouse ──
    {"slug": "stripe", "ats": "greenhouse"},
    {"slug": "airbnb", "ats": "greenhouse"},
    {"slug": "datadog", "ats": "greenhouse"},
    {"slug": "cloudflare", "ats": "greenhouse"},
    {"slug": "figma", "ats": "greenhouse"},
    {"slug": "asana", "ats": "greenhouse"},
    {"slug": "gitlab", "ats": "greenhouse"},
    {"slug": "dropbox", "ats": "greenhouse"},
    {"slug": "vercel", "ats": "greenhouse"},
    {"slug": "postman", "ats": "greenhouse"},
    {"slug": "brex", "ats": "greenhouse"},
    {"slug": "coinbase", "ats": "greenhouse"},
    {"slug": "robinhood", "ats": "greenhouse"},
    {"slug": "reddit", "ats": "greenhouse"},
    {"slug": "discord", "ats": "greenhouse"},
    {"slug": "twilio", "ats": "greenhouse"},
    {"slug": "instacart", "ats": "greenhouse"},
    {"slug": "lyft", "ats": "greenhouse"},
    {"slug": "pinterest", "ats": "greenhouse"},
    {"slug": "mongodb", "ats": "greenhouse"},
    {"slug": "anthropic", "ats": "greenhouse"},
    # ── Ashby ──
    {"slug": "linear", "ats": "ashby"},
    {"slug": "replit", "ats": "ashby"},
    {"slug": "modal", "ats": "ashby"},
    {"slug": "supabase", "ats": "ashby"},
    {"slug": "baseten", "ats": "ashby"},
    {"slug": "perplexity", "ats": "ashby"},
    {"slug": "ramp", "ats": "ashby"},
]

# Locations we treat as "anywhere the user is OK with" when their filter is
# India or unset. Any job whose location string contains one of these is kept.
REMOTE_KEYWORDS = ("remote", "anywhere", "worldwide", "wfh", "work from home")

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def _clean(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", (s or "")).strip()


def _location_match(job_location: str, user_location: str) -> bool:
    """Keep a job if its location matches what the user wants. Lenient by
    design — a missed match is worse than an extra job to scroll past.
    """
    jl = (job_location or "").lower()
    ul = (user_location or "india").lower().strip()

    # User wants any location — keep all
    if not ul or ul in ("any", "anywhere", "worldwide"):
        return True

    # Always keep remote roles regardless of user filter
    if any(k in jl for k in REMOTE_KEYWORDS):
        return True

    # India-anchored search — match Indian city names + "india"
    if ul in ("india", "in"):
        india_cities = (
            "india", "bangalore", "bengaluru", "mumbai", "hyderabad",
            "chennai", "delhi", "noida", "gurgaon", "gurugram", "pune",
            "kolkata", "ahmedabad", "jaipur", "kochi",
        )
        return any(c in jl for c in india_cities)

    # Otherwise: substring match on the user's filter
    return ul in jl


def _fetch_json(url: str, timeout: float = 10.0) -> dict | None:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 JobAgent"}, timeout=timeout)
        if r.status_code != 200:
            logger.debug(f"[ATS] {url} → HTTP {r.status_code}")
            return None
        return r.json()
    except Exception as e:
        logger.debug(f"[ATS] {url} fetch failed: {e}")
        return None


def _greenhouse_jobs(slug: str) -> list[dict]:
    data = _fetch_json(GREENHOUSE_URL.format(slug=slug))
    if not data or "jobs" not in data:
        return []
    out = []
    for j in data["jobs"]:
        out.append({
            "company_slug": slug,
            "company_name": slug.title(),
            "ats": "greenhouse",
            "external_id": str(j.get("id")),
            "title": j.get("title", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "url": j.get("absolute_url", ""),
            "description_html": j.get("content", ""),
            "updated_at": j.get("updated_at"),
        })
    return out


def _ashby_jobs(slug: str) -> list[dict]:
    data = _fetch_json(ASHBY_URL.format(slug=slug))
    if not data or "jobs" not in data:
        return []
    out = []
    for j in data["jobs"]:
        loc = j.get("locationName") or ""
        if j.get("isRemote") and "remote" not in loc.lower():
            loc = (loc + " (Remote)").strip()
        out.append({
            "company_slug": slug,
            "company_name": slug.title(),
            "ats": "ashby",
            "external_id": str(j.get("id")),
            "title": j.get("title", ""),
            "location": loc,
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "description_html": j.get("descriptionHtml") or j.get("description") or "",
            "updated_at": j.get("publishedAt") or j.get("updatedAt"),
        })
    return out


def _fetch_all_companies() -> list[dict]:
    """Hit every company in COMPANIES sequentially. Cheap (~40 HTTP calls,
    ~5s total). If we ever scale this up we can use httpx.AsyncClient + gather.
    """
    rows: list[dict] = []
    for c in COMPANIES:
        if c["ats"] == "greenhouse":
            jobs = _greenhouse_jobs(c["slug"])
        elif c["ats"] == "ashby":
            jobs = _ashby_jobs(c["slug"])
        else:
            jobs = []
        if jobs:
            logger.debug(f"[ATS] {c['slug']} ({c['ats']}): {len(jobs)} jobs")
        else:
            logger.debug(f"[ATS] {c['slug']} ({c['ats']}): 0 (slug may have moved)")
        rows.extend(jobs)
    return rows


class ATSAggregatorAgent(BaseAgent):
    platform = "ats"
    # Discovery is pure HTTP. Apply opens a Playwright window, but we lazy-init
    # it so discovery never spawns a browser at all.
    requires_visible_browser = False

    async def start(self, headless: bool = False):
        # Don't launch a browser at start time — discovery never needs one.
        # apply_to_job will spin up Playwright on demand via _ensure_browser().
        self._headless_pref = False  # apply always wants visible
        logger.info("[ATS] Aggregator ready (no browser yet — lazy)")

    async def _ensure_browser(self):
        if self._page is None:
            await super().start(headless=False)

    async def login(self) -> bool:
        # No auth — public APIs.
        return True

    async def search_jobs(
        self,
        keywords: list[str],
        location: str,
        filters: dict,
        max_jobs: int = 40,
    ) -> list[dict]:
        # Run the synchronous HTTP fan-out off the event loop so we don't
        # block the agent thread while waiting on ~40 sequential requests.
        rows = await asyncio.to_thread(_fetch_all_companies)
        if not rows:
            logger.warning("[ATS] No jobs returned from any board")
            return []

        kws = [k.lower() for k in (keywords or []) if k.strip()]
        results: list[dict] = []
        for r in rows:
            title_l = (r["title"] or "").lower()
            if kws and not any(kw in title_l for kw in kws):
                continue
            if not _location_match(r["location"], location):
                continue

            job_id = f"ats_{r['ats']}_{r['company_slug']}_{r['external_id']}"
            results.append({
                "job_id": job_id,
                "platform": "ats",
                "title": r["title"],
                "company": r["company_name"],
                "location": r["location"] or "",
                "url": r["url"],
                "description": _clean(r["description_html"])[:6000],
                "easy_apply": False,
                # V1: ATS aggregator URLs are off-board (Greenhouse / Ashby tenants)
                "apply_channel": "external",
                "external_apply_url": r["url"],
                # Stash for the apply phase
                "_ats": r["ats"],
                "_company_slug": r["company_slug"],
            })
            if len(results) >= max_jobs:
                break

        logger.info(
            f"[ATS] {len(rows)} total → {len(results)} match keyword/location filters"
        )
        return results

    async def get_description(self, url: str) -> str:
        # Greenhouse + Ashby ship the full description in the listing payload,
        # so this is mostly a no-op. Returning empty lets the orchestrator
        # fall back to whatever was inlined at search time.
        return ""

    async def apply_to_job(self, job: dict) -> str:
        """Open the job's apply URL in a visible browser, attempt to fill
        common form fields, then leave the page open for the user to submit.

        ATS platforms use very different form layouts, so this is a best-
        effort generic filler. Greenhouse uses standard <input> elements;
        Ashby uses React-driven custom widgets. The user ALWAYS clicks the
        final submit themselves.
        """
        title = job.get("title", "?")
        url = job.get("url", "")
        if not url:
            return "skipped"
        try:
            await self._ensure_browser()
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self.human_delay(2, 3)
            # V1: prefer the shared UniversalFormFiller — falls back to the
            # legacy generic filler if it didn't fill anything (defensive).
            from .universal_filler import UniversalFormFiller
            uff = UniversalFormFiller(self.page, self.profile)
            uff_result = await uff.run()
            logger.info(
                f"[ATS] UniversalFormFiller — pages={uff_result.pages_filled} "
                f"filled={uff_result.fields_filled} reached_review={uff_result.reached_review} "
                f"reason={uff_result.reason!r}"
            )
            if uff_result.fields_filled == 0:
                logger.info("[ATS] UFF filled nothing — falling back to legacy generic filler")
                await self._fill_generic_form()
            logger.info(
                f"[ATS] Form auto-filled. Review and click final Submit "
                f"in the browser (waiting up to 120s): {title}"
            )

            # Wait for the user to submit. Detect via URL change or success text.
            success_signals = [
                "text=/thank you for applying/i",
                "text=/application submitted/i",
                "text=/we[' ]?ve received your application/i",
                "text=/successfully\\s+applied/i",
            ]
            start_url = self.page.url
            elapsed = 0.0
            while elapsed < 120:
                for sig in success_signals:
                    try:
                        if await self.page.locator(sig).first.is_visible(timeout=200):
                            return "applied"
                    except Exception:
                        pass
                # URL change away from the apply form → likely submitted
                cur = self.page.url
                if cur != start_url and not _is_same_apply_page(start_url, cur):
                    return "applied"
                await asyncio.sleep(1.5)
                elapsed += 1.5
            return "skipped"
        except Exception as e:
            logger.error(f"[ATS] apply error: {e}")
            return "failed"

    # ── Generic ATS form filler ──────────────────────────────────────────

    async def _fill_generic_form(self):
        p = self.profile
        first = (p.get("full_name") or "").split()[0] if p.get("full_name") else ""
        last = (p.get("full_name") or "").split()[-1] if p.get("full_name") else ""
        profile_map = {
            "first name": first,
            "given name": first,
            "last name": last,
            "family name": last,
            "full name": p.get("full_name", ""),
            "name": p.get("full_name", ""),
            "email": p.get("email", ""),
            "phone": p.get("phone", ""),
            "mobile": p.get("phone", ""),
            "city": p.get("city", ""),
            "current location": p.get("city", ""),
            "linkedin": p.get("linkedin_url", ""),
            "portfolio": p.get("portfolio_url", ""),
            "website": p.get("portfolio_url", ""),
            "current title": p.get("current_title", ""),
            "current company": p.get("current_company", ""),
            "years": str(p.get("years_of_experience", "") or ""),
            "experience": str(p.get("years_of_experience", "") or ""),
        }
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
                    if (await inp.input_value()).strip():
                        continue

                    bits = []
                    for attr in ("placeholder", "name", "id", "aria-label", "title"):
                        v = await inp.get_attribute(attr)
                        if v:
                            bits.append(v)
                    fid = await inp.get_attribute("id")
                    if fid:
                        try:
                            lbl = self.page.locator(f"label[for='{fid}']").first
                            if await lbl.count() > 0:
                                bits.append(await lbl.inner_text())
                        except Exception:
                            pass
                    hint = " ".join(bits).lower()

                    fill_val = ""
                    for key in sorted(profile_map.keys(), key=len, reverse=True):
                        if key in hint and profile_map[key]:
                            fill_val = str(profile_map[key])
                            break
                    if not fill_val:
                        continue
                    await inp.fill(fill_val)
                    await self.human_delay(0.15, 0.4)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[ATS] _fill_generic_form: {e}")


def _is_same_apply_page(a: str, b: str) -> bool:
    """Treat URL changes within the same apply form (e.g. multi-step pages
    on the same host/path-prefix) as 'still in the apply flow'."""
    pa, pb = urlparse(a), urlparse(b)
    return pa.netloc == pb.netloc and pa.path.split("/")[:4] == pb.path.split("/")[:4]
