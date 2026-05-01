"""Probe Naukri's rendered DOM to find stable selectors.

Loads a search URL via Playwright, waits for content to render, then prints:
  - the URL we ended up on
  - the count of <a href="*job-listings-*"> links (Naukri's stable per-job URL pattern)
  - up to 3 sample job links with their parent container class
  - any data-* attributes on those parents
"""
import asyncio
import sys

# Windows: Playwright requires ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright


async def main():
    url = "https://www.naukri.com/product-manager-jobs-1"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            viewport={"width": 1366, "height": 900},
        )
        # Hide webdriver flag
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await ctx.new_page()
        print(f"GOTO: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait for the job list to render. The splash uses .styles_splScrn__*; we wait for it to disappear.
        try:
            await page.wait_for_selector("a[href*='/job-listings-']", timeout=20000)
            print("OK: at least one job link rendered")
        except Exception as e:
            print(f"WAIT FAIL: {e}")
        print(f"FINAL URL: {page.url}")

        # Count job-listing links
        links = await page.locator("a[href*='/job-listings-']").all()
        print(f"JOB LINKS FOUND: {len(links)}")

        # Sample first 3
        for i, link in enumerate(links[:3]):
            try:
                href = await link.get_attribute("href")
                text = (await link.inner_text()).strip()[:80]
                # Try to find a stable parent container
                parent_tag = await link.evaluate(
                    "(el) => { let p = el; for (let i = 0; i < 6; i++) { p = p.parentElement; if (!p) break; if (p.getAttribute('data-job-id') || (p.className && p.className.includes('Tuple'))) return {tag: p.tagName, cls: p.className, jid: p.getAttribute('data-job-id')}; } return null; }"
                )
                print(f"  [{i}] href={href}")
                print(f"      text={text}")
                print(f"      parent={parent_tag}")
            except Exception as e:
                print(f"  [{i}] error: {e}")

        # Also dump first 3 articles or divs with data-job-id
        cards = await page.locator("[data-job-id]").all()
        print(f"[data-job-id] CARDS: {len(cards)}")
        for i, card in enumerate(cards[:3]):
            jid = await card.get_attribute("data-job-id")
            cls = await card.get_attribute("class")
            print(f"  [{i}] id={jid} class={cls}")

        # Save a screenshot + body HTML preview for diagnosis
        await page.screenshot(path="tests/screenshots/probe_naukri.png", full_page=True)
        html = await page.content()
        print("HTML LEN:", len(html))
        print("BODY SNIPPET:", html[:500].replace("\n", " "))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
