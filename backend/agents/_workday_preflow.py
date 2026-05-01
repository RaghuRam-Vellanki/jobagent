"""
Workday entry quirk: their tenant pages start with a social-login chooser
("Apply with LinkedIn", "Apply with Indeed", "Apply Manually"). Once
"Apply Manually" is clicked, the regular form flow loads and the shared
UniversalFormFiller takes over.

Kept intentionally tiny per V1 spec.
"""
from __future__ import annotations
import logging
from playwright.async_api import Page

logger = logging.getLogger("agent.workday_preflow")


def is_workday_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    return "myworkdayjobs.com" in u or "wd1.myworkday" in u or "wd5.myworkday" in u


async def run(page: Page) -> bool:
    """If we're on a Workday tenant landing page, click 'Apply Manually'.
    Returns True if we clicked it (or if no preflow was needed)."""
    try:
        if not is_workday_url(page.url):
            return True
        for sel in [
            "button:has-text('Apply Manually')",
            "a:has-text('Apply Manually')",
            "[data-automation-id='applyManually']",
        ]:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    logger.info("[workday] clicked Apply Manually")
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    return True
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"[workday] preflow error: {e}")
    return True
