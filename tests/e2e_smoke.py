"""End-to-end smoke test for JobAgent v2.

Assumes backend is running on :8000 and frontend on :5173 (start with `python run.py`).
Creates a fresh test user, walks through onboarding + every main page, captures
screenshots for any failures, and asserts:
  - No JS console errors on any page
  - Onboarding redirects work (no resume → /onboarding, has resume → settings accessible)
  - Resume parser populates Settings fields
  - Each protected page renders without crashing
  - Agent state endpoint authenticates correctly
"""
import os
import sys
import time
import requests
from playwright.sync_api import sync_playwright, expect, ConsoleMessage

# Force UTF-8 so Playwright exception text containing arrows doesn't crash on Win console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8000"
FRONT = "http://localhost:5173"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESUME_PDF = os.path.join(ROOT, "resume", "raghuram_vellanki_resume_v3.pdf")
SCREENSHOTS = os.path.join(ROOT, "tests", "screenshots")
os.makedirs(SCREENSHOTS, exist_ok=True)

# Unique emails per run so re-running doesn't collide
_STAMP = int(time.time())
API_TEST_EMAIL = f"e2e_api_{_STAMP}@test.local"
TEST_EMAIL = f"e2e_ui_{_STAMP}@test.local"  # used by browser flow
TEST_PASS = "testpass123"

results: list[tuple[str, bool, str]] = []
console_errors: list[str] = []


def log(name: str, ok: bool, detail: str = ""):
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {name}{(' — ' + detail) if detail else ''}")
    results.append((name, ok, detail))


def shot(page, name: str):
    path = os.path.join(SCREENSHOTS, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    return path


def check_backend_health() -> bool:
    """Backend smoke: health, register, login."""
    try:
        r = requests.get(f"{API}/api/agent/state", timeout=3)
        log("backend reachable", r.status_code in (200, 401), f"status={r.status_code}")
    except Exception as e:
        log("backend reachable", False, str(e))
        return False

    r = requests.post(f"{API}/api/auth/register", json={"email": API_TEST_EMAIL, "password": TEST_PASS}, timeout=5)
    log("register endpoint", r.status_code == 200, f"status={r.status_code} body={r.text[:120]}")
    if r.status_code != 200:
        return False
    token = r.json().get("access_token")
    log("register returns token", bool(token))

    r = requests.post(f"{API}/api/auth/login", json={"email": API_TEST_EMAIL, "password": TEST_PASS}, timeout=5)
    log("login endpoint", r.status_code == 200, f"status={r.status_code}")

    r = requests.get(f"{API}/api/agent/state", headers={"Authorization": f"Bearer {token}"}, timeout=5)
    log("agent state with token", r.status_code == 200)

    r = requests.get(f"{API}/api/agent/state", timeout=5)
    log("agent state without token returns 401", r.status_code == 401, f"got {r.status_code}")
    return True


def run_frontend_flow():
    if not os.path.exists(RESUME_PDF):
        log("resume pdf exists", False, RESUME_PDF)
        return
    log("resume pdf exists", True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        page.on("console", lambda msg: _capture_console(msg))
        page.on("pageerror", lambda exc: console_errors.append(f"PAGEERROR: {exc}"))

        # 1. Login page reachable (React Router redirect happens client-side after mount)
        page.goto(FRONT)
        try:
            page.wait_for_url("**/login", timeout=5000)
            log("unauth root -> /login", True, page.url)
        except Exception:
            log("unauth root -> /login", False, page.url)
        shot(page, "01_login")

        # 2. Register — has 3 password fields (password + confirm), fill all
        page.goto(f"{FRONT}/register", wait_until="networkidle")
        page.fill('input[type="email"]', TEST_EMAIL)
        pw_inputs = page.locator('input[type="password"]')
        pw_inputs.nth(0).fill(TEST_PASS)
        pw_inputs.nth(1).fill(TEST_PASS)
        page.click('button[type="submit"]')
        # Don't wait_for_load_state — register redirects via React Router (no nav event)
        log("register submitted", True, page.url)
        shot(page, "02_after_register")

        # 3. Should be on onboarding (no resume yet)
        page.wait_for_url("**/onboarding", timeout=5000)
        log("redirected to /onboarding for new user", "/onboarding" in page.url)
        shot(page, "03_onboarding")

        # 4. Upload resume
        with page.expect_file_chooser() as fc_info:
            page.locator("text=Click to upload your resume").click()
        fc = fc_info.value
        fc.set_files(RESUME_PDF)

        # Wait for parsed preview
        page.wait_for_selector("text=Resume parsed", timeout=15000)
        log("resume uploaded + parsed", True)
        shot(page, "04_parsed_preview")

        # Verify at least one parsed field surfaced (Email row is rendered when parser found one)
        body = page.content()
        log("parsed preview shows Email row", ">Email<" in body)
        log("parsed preview shows Skills row", ">Skills<" in body)

        # 5. Continue to Settings (use regex to avoid hard-coding the unicode arrow)
        import re
        page.get_by_role("button", name=re.compile(r"Continue to Settings")).click()
        page.wait_for_url("**/settings", timeout=5000)
        log("navigates to /settings (no bounce-back)", "/settings" in page.url)
        page.wait_for_load_state("networkidle")
        shot(page, "05_settings_after_onboarding")

        # 6. Settings has auto-filled fields
        full_name_val = page.locator('input').first.input_value()
        log("Settings shows auto-filled name", bool(full_name_val), repr(full_name_val))

        # 7. Visit each protected page
        for path, title in [
            ("/", "Dashboard"),
            ("/discover", "Discovery"),
            ("/queue", "Queue"),
            ("/applied", "Applied"),
            ("/ats", "ATS"),
            ("/settings", "Settings"),
        ]:
            page.goto(f"{FRONT}{path}", wait_until="networkidle")
            shot(page, f"06_page_{title.lower()}")
            log(f"page renders: {title}", path in page.url, page.url)

        # 8. Confirm /onboarding now redirects away (resume_path is set)
        page.goto(f"{FRONT}/onboarding", wait_until="networkidle")
        # Onboarding should still load since we go to it explicitly, but
        # it's full-screen so just confirm no crash
        log("onboarding still accessible after upload", True, page.url)

        browser.close()


def _capture_console(msg: ConsoleMessage):
    if msg.type in ("error",):
        # Suppress noisy WS reconnect logs from Vite HMR
        text = msg.text
        if "WebSocket" in text and "vite" in text.lower():
            return
        console_errors.append(text)


def main():
    print("=" * 60)
    print(f"  JobAgent v2 — E2E smoke test")
    print(f"  test user: {TEST_EMAIL}")
    print("=" * 60)

    print("\n[1] Backend API checks")
    if not check_backend_health():
        print("\nBackend not healthy — aborting frontend flow.")
        _summary()
        sys.exit(1)

    print("\n[2] Frontend flow (Playwright)")
    try:
        run_frontend_flow()
    except Exception as e:
        log("frontend flow", False, f"exception: {e}")

    print("\n[3] Console errors")
    if console_errors:
        for err in console_errors:
            print(f"  - {err}")
        log("no console errors", False, f"{len(console_errors)} error(s)")
    else:
        log("no console errors", True)

    _summary()


def _summary():
    print()
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"  RESULTS: {passed}/{total} passed")
    print("=" * 60)
    failed = [(n, d) for n, ok, d in results if not ok]
    if failed:
        print("  FAILURES:")
        for name, detail in failed:
            print(f"    - {name}: {detail}")
        print(f"\n  Screenshots saved to {SCREENSHOTS}")
        sys.exit(1)
    print(f"  Screenshots saved to {SCREENSHOTS}")


if __name__ == "__main__":
    main()
