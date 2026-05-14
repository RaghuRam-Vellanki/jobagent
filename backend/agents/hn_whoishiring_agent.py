"""HackerNews "Who Is Hiring" agent — V1.3 Brief mode.

Fetches the most recent monthly "Ask HN: Who is hiring?" thread via the
HN Algolia API (cleaner than scraping news.ycombinator.com), parses each
top-level comment into a job record, and filters by user keywords.

No Playwright needed — pure httpx + BeautifulSoup4. Public read-only API.
"""
from __future__ import annotations

import logging
import re
import hashlib
from html import unescape

logger = logging.getLogger("agent.hn")

HN_SEARCH = "https://hn.algolia.com/api/v1/search?query=Ask+HN+Who+is+hiring&tags=story&hitsPerPage=5"
HN_ITEM = "https://hn.algolia.com/api/v1/items/{}"


class HNWhoIsHiringAgent:
    """Brief-only agent — doesn't subclass BaseAgent because it needs no browser."""
    platform = "hn"
    requires_visible_browser = False

    def __init__(self, profile: dict, credentials: dict):
        self.profile = profile
        self.credentials = credentials

    async def start(self, headless: bool = True):
        return

    async def stop(self):
        return

    async def login(self) -> bool:
        return True

    async def search_jobs(
        self,
        keywords: list[str],
        location: str,
        filters: dict,
        max_jobs: int = 30,
    ) -> list[dict]:
        try:
            import httpx
        except Exception as e:
            logger.warning(f"[hn] httpx unavailable: {e}")
            return []

        kws = [k.lower().strip() for k in (keywords or []) if k.strip()]
        loc_l = (location or "").lower()
        india_signals = ["india", "bengaluru", "bangalore", "hyderabad", "delhi",
                         "ncr", "mumbai", "pune", "remote"]

        async with httpx.AsyncClient(timeout=15.0) as client:
            # Find the most recent Who-Is-Hiring thread
            try:
                r = await client.get(HN_SEARCH)
                r.raise_for_status()
                hits = r.json().get("hits", [])
            except Exception as e:
                logger.warning(f"[hn] search failed: {e}")
                return []

            thread_id = None
            for h in hits:
                title = (h.get("title") or "").lower()
                if "who is hiring" in title and "ask hn" in title:
                    thread_id = h.get("objectID")
                    break
            if not thread_id:
                logger.info("[hn] no recent 'Who is hiring' thread found")
                return []

            # Fetch the thread with all comments
            try:
                r = await client.get(HN_ITEM.format(thread_id))
                r.raise_for_status()
                thread = r.json()
            except Exception as e:
                logger.warning(f"[hn] thread fetch failed: {e}")
                return []

        comments = thread.get("children", []) or []
        jobs: list[dict] = []

        for c in comments:
            if len(jobs) >= max_jobs:
                break
            text_html = c.get("text") or ""
            if not text_html:
                continue
            text = _strip_html(text_html)
            text_l = text.lower()

            # Keyword filter — first line typically has the role title.
            if kws and not any(kw in text_l for kw in kws):
                continue

            # India / remote filter — Brief is India-first.
            if loc_l and not any(s in text_l for s in india_signals):
                continue

            parsed = _parse_comment(text, c.get("author", ""))
            if not parsed:
                continue
            jobs.append(parsed)

        logger.info(f"[hn] yielded {len(jobs)} jobs from thread {thread_id}")
        return jobs


# ── parsing helpers ─────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://[^\s<>\"')]+")
_PIPE_SPLIT = re.compile(r"\s*\|\s*")


def _strip_html(s: str) -> str:
    s = _TAG_RE.sub(" ", s)
    s = unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_comment(text: str, author: str) -> dict | None:
    """HN "Who is hiring" convention: first line is the pitch, usually
    `Company | Role | Location | (Remote OK) | URL` or some variant."""
    if not text or len(text) < 20:
        return None
    first = text.split(".")[0][:300]

    company = ""
    title = ""
    location = ""
    parts = _PIPE_SPLIT.split(first)
    if len(parts) >= 2:
        company = parts[0].strip()
        title = parts[1].strip()
        if len(parts) >= 3:
            location = parts[2].strip()
    else:
        # Fallback: first 60 chars as the pitch, no clean split
        company = first[:60].strip()
        title = first[:80].strip()

    # URL = first link in the body
    m = _URL_RE.search(text)
    url = m.group(0) if m else "https://news.ycombinator.com/item?id=" + author

    job_id = "hn_" + hashlib.md5((company + title + url).encode()).hexdigest()[:12]

    return {
        "job_id": job_id,
        "platform": "hn",
        "title": title or "Engineer",
        "company": company or "Unknown",
        "location": location or "Remote",
        "url": url,
        "description": text[:1500],
        "easy_apply": False,
        "apply_channel": "external",
    }
