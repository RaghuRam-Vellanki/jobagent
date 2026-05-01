"""Probe Google Jobs, Indeed India, and Wellfound to find stable selectors.

Each section:
  - loads the search URL
  - waits for content
  - prints up to 3 sample job cards with class/href/text
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright


async def open_browser(p):
    browser = await p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        viewport={"width": 1366, "height": 900},
    )
    await ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return browser, ctx


async def probe_google(ctx):
    print("\n=== GOOGLE JOBS ===")
    page = await ctx.new_page()
    url = "https://www.google.com/search?q=product+manager+jobs+in+india&ibp=htl;jobs"
    print(f"GOTO: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        # Two known patterns: legacy `.iFjolb` cards and newer `.EimVGf` / `[role='listitem']`
        cands = await page.evaluate("""
            () => {
                const out = [];
                const candidates = document.querySelectorAll('[role="listitem"], li.iFjolb, .EimVGf, .pE8vnd, [jsname]');
                for (const el of candidates) {
                    const t = (el.innerText || '').trim();
                    if (t.length > 50 && t.length < 800) {
                        out.push({
                            tag: el.tagName,
                            cls: (el.className || '').slice(0, 80),
                            attrs: Array.from(el.attributes).filter(a => a.name.startsWith('jsname') || a.name === 'role').map(a => `${a.name}=${a.value}`).join(','),
                            preview: t.replace(/\\s+/g, ' ').slice(0, 200),
                        });
                    }
                }
                return out.slice(0, 5);
            }
        """)
        for i, c in enumerate(cands):
            print(f"  [{i}] {c['tag']} cls={c['cls']!r} attrs={c['attrs']}")
            print(f"      preview={c['preview']!r}")
        # Try to find jobs widget link (Google sometimes shows a full Jobs vertical)
        jobs_link = await page.evaluate("() => Array.from(document.querySelectorAll('a')).filter(a => /jobs/i.test(a.href)).slice(0,3).map(a => a.href)")
        print(f"  job links: {jobs_link[:3]}")
    except Exception as e:
        print(f"  ERROR: {e}")
    await page.close()


async def probe_indeed(ctx):
    print("\n=== INDEED INDIA ===")
    page = await ctx.new_page()
    url = "https://in.indeed.com/jobs?q=product+manager&l=India"
    print(f"GOTO: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        cands = await page.evaluate("""
            () => {
                const out = [];
                const sels = ['div.job_seen_beacon', 'div.cardOutline', 'a.tapItem', '[data-testid="job-result"]', '.jobsearch-SerpJobCard', '[data-jk]'];
                for (const s of sels) {
                    const els = document.querySelectorAll(s);
                    if (els.length > 0) {
                        out.push({selector: s, count: els.length});
                        for (let i = 0; i < Math.min(els.length, 2); i++) {
                            const el = els[i];
                            const t = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200);
                            const titleEl = el.querySelector('h2 a, [data-testid="jobTitle"], a.jcs-JobTitle');
                            out.push({
                                idx: i,
                                jk: el.getAttribute('data-jk'),
                                title: titleEl ? titleEl.innerText.trim() : '',
                                href: titleEl ? titleEl.getAttribute('href') : '',
                                preview: t,
                            });
                        }
                        break;
                    }
                }
                return out;
            }
        """)
        for c in cands:
            print(f"  {c}")
    except Exception as e:
        print(f"  ERROR: {e}")
    await page.close()


async def probe_wellfound(ctx):
    print("\n=== WELLFOUND ===")
    page = await ctx.new_page()
    url = "https://wellfound.com/role/l/product-manager/india"
    print(f"GOTO: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        cands = await page.evaluate("""
            () => {
                const out = [];
                // Wellfound uses Tailwind utility classes; look for job link pattern
                const links = document.querySelectorAll('a[href*="/jobs/"], a[href*="/company/"][href*="/jobs"]');
                out.push({total_jobs_links: links.length});
                const sample = Array.from(links).slice(0, 5).map(a => ({
                    href: a.href,
                    text: (a.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 100),
                    parent_cls: (a.closest('[class*="styles"], [class*="JobCard"], div')?.className || '').slice(0, 80),
                }));
                out.push({samples: sample});
                return out;
            }
        """)
        for c in cands:
            print(f"  {c}")
    except Exception as e:
        print(f"  ERROR: {e}")
    await page.close()


async def main():
    async with async_playwright() as p:
        browser, ctx = await open_browser(p)
        try:
            await probe_google(ctx)
            await probe_indeed(ctx)
            await probe_wellfound(ctx)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
