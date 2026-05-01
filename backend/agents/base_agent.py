"""
BaseAgent — shared Playwright browser utilities and human-like helpers.
All platform agents inherit from this.
"""
import asyncio
import random
import logging
import os
from abc import ABC, abstractmethod
from typing import AsyncGenerator

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

logger = logging.getLogger("agent.base")


class BaseAgent(ABC):
    platform: str = "base"
    # Some sites (Naukri) detect headless Chromium and serve a blank page.
    # Subclasses can override this to force a visible browser window.
    requires_visible_browser: bool = False

    def __init__(self, profile: dict, credentials: dict):
        self.profile = profile
        self.credentials = credentials
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ── Browser lifecycle ────────────────────────────────────────────

    async def start(self, headless: bool = False):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-notifications",
                "--window-size=1280,900",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        # Hide webdriver fingerprint
        await self._context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        self._page = await self._context.new_page()
        logger.info(f"[{self.platform}] Browser started (headless={headless})")

    async def stop(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.debug(f"[{self.platform}] stop error: {e}")

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started — call await agent.start() first")
        return self._page

    # ── Human-like helpers ───────────────────────────────────────────

    async def human_delay(self, lo: float = 1.0, hi: float = 3.0):
        await asyncio.sleep(random.uniform(lo, hi))

    async def human_type(self, selector: str, text: str):
        await self.page.click(selector)
        for ch in text:
            await self.page.keyboard.type(ch, delay=random.randint(40, 130))

    async def safe_fill(self, selector: str, value: str):
        try:
            el = self.page.locator(selector).first
            await el.scroll_into_view_if_needed()
            await el.fill(value)
        except Exception as e:
            logger.debug(f"safe_fill({selector}): {e}")

    async def safe_click(self, selector: str, timeout: int = 5000) -> bool:
        try:
            el = self.page.locator(selector).first
            await el.wait_for(state="visible", timeout=timeout)
            await el.scroll_into_view_if_needed()
            await el.click()
            return True
        except Exception:
            return False

    async def get_text(self, selector: str, default: str = "") -> str:
        try:
            return (await self.page.locator(selector).first.inner_text()).strip()
        except Exception:
            return default

    # ── Abstract interface ───────────────────────────────────────────

    @abstractmethod
    async def login(self) -> bool:
        """Log into the platform. Returns True on success."""
        ...

    @abstractmethod
    async def search_jobs(
        self,
        keywords: list[str],
        location: str,
        filters: dict,
        max_jobs: int = 40,
    ) -> list[dict]:
        """Scrape job listings. Returns list of job dicts."""
        ...

    @abstractmethod
    async def apply_to_job(self, job: dict) -> str:
        """Apply to a single job. Returns 'applied' | 'failed' | 'skipped'."""
        ...
