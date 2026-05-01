"""Probe Naukri job-detail page DOM to find the description container."""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright


async def main():
    url = "https://www.naukri.com/job-listings-product-manager-google-india-private-limited-bengaluru-5-to-10-years-090725503785"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        )
        await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait for any element with substantial text
        try:
            await page.wait_for_selector("section, [class*='job-desc'], [class*='JobDesc'], [class*='styles_JDC']", timeout=20000)
        except Exception as e:
            print("WAIT FAIL:", e)

        # Find any <section> or <div> with > 200 chars text and dump its outer class names
        candidates = await page.evaluate("""
            () => {
                const out = [];
                const els = document.querySelectorAll('section, div');
                for (const el of els) {
                    const t = (el.innerText || '').trim();
                    if (t.length > 300 && t.length < 5000) {
                        out.push({
                            tag: el.tagName,
                            cls: el.className,
                            id: el.id,
                            len: t.length,
                            preview: t.slice(0, 100),
                        });
                    }
                }
                // Sort by length descending, return top 5
                out.sort((a, b) => b.len - a.len);
                return out.slice(0, 8);
            }
        """)
        for i, c in enumerate(candidates):
            print(f"[{i}] tag={c['tag']} id={c['id']} len={c['len']}")
            print(f"    cls={c['cls'][:120]}")
            print(f"    preview={c['preview'][:120]!r}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
