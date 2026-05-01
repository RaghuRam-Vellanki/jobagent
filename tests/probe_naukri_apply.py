"""Probe the Naukri job-detail page to find stable apply-button selectors."""
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
        await asyncio.sleep(4)  # let SPA hydrate

        # Find every clickable element whose text contains "apply"
        cands = await page.evaluate("""
            () => {
                const out = [];
                const els = document.querySelectorAll('button, a, div[role="button"]');
                for (const el of els) {
                    const txt = (el.innerText || '').trim();
                    if (txt.length > 0 && txt.length < 60 && /apply/i.test(txt)) {
                        out.push({
                            tag: el.tagName,
                            text: txt.replace(/\\s+/g, ' '),
                            id: el.id,
                            cls: el.className,
                            href: el.getAttribute('href') || '',
                        });
                    }
                }
                return out.slice(0, 12);
            }
        """)
        for i, c in enumerate(cands):
            print(f"[{i}] {c['tag']} text={c['text']!r}")
            print(f"    id={c['id']}  cls={c['cls'][:120]}")
            if c['href']:
                print(f"    href={c['href'][:120]}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
