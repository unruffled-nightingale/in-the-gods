"""Headless Chromium for venues whose listings never appear in the raw HTML.

Wix hashed classes, TicketSolve booths, Nuxt shells and Cloudflare
interstitials all look empty to requests.get. One Playwright context is
kept for the process and reused across hops, because spinning Chromium
per URL would make the weekly job a nuisance.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

# Prefer a repo-local install (`.playwright/`) when CI's default cache is
# missing. Must be set before Playwright starts.
_LOCAL_BROWSERS = Path(__file__).resolve().parents[1] / ".playwright"
if _LOCAL_BROWSERS.is_dir() and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_LOCAL_BROWSERS)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

# Cloudflare, TicketSource and similar bot-walls.
_CHALLENGE = re.compile(
    r"just a moment|checking (?:if )?your (?:connection|browser)|"
    r"enable javascript and cookies|attention required|"
    r"cf-browser-verification|verify you are human|"
    r"connectyourdomain",
    re.I,
)

_play = None
_browser = None
_ctx = None

# Playwright's bundled Chromium is what CI installs. Dev machines often
# only have Google Chrome, and recent Playwright looks for
# chrome-headless-shell which `playwright install chromium` may not have
# left behind.
_CHROME_BINS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
)


def _launch_browser(play):
    """Launch Chromium, falling back to a system Chrome if needed."""
    last = None
    attempts = []
    bundled = Path(play.chromium.executable_path)
    if bundled.is_file():
        attempts.append({"executable_path": str(bundled)})
    attempts.append({})
    attempts.append({"channel": "chrome"})
    attempts.append({"channel": "chromium"})
    for path in _CHROME_BINS:
        if Path(path).is_file():
            attempts.append({"executable_path": path})
    seen = set()
    for kwargs in attempts:
        key = tuple(sorted(kwargs.items()))
        if key in seen:
            continue
        seen.add(key)
        try:
            return play.chromium.launch(headless=True, **kwargs)
        except Exception as e:                                # noqa: BLE001
            last = e
    raise last


def get_context():
    """Lazy Chromium, one per process."""
    global _play, _browser, _ctx
    if _ctx is not None:
        return _ctx
    from playwright.sync_api import sync_playwright
    _play = sync_playwright().start()
    _browser = _launch_browser(_play)
    _ctx = _browser.new_context(
        user_agent=UA,
        locale="en-GB",
        timezone_id="Europe/London",
        viewport={"width": 1280, "height": 1800},
    )
    # the flag most bot-walls look for first
    _ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return _ctx


def close():
    """Shut Chromium down. fetch.run calls this in a finally."""
    global _play, _browser, _ctx
    if _ctx is not None:
        _ctx.close()
        _ctx = None
    if _browser is not None:
        _browser.close()
        _browser = None
    if _play is not None:
        _play.stop()
        _play = None


def _still_challenging(html):
    if len(html) < 800:
        return True
    head = html[:4000]
    return bool(_CHALLENGE.search(head))


def _dismiss_cookies(page):
    """Cookie banners sit on top of the listing and swallow the clicks we need."""
    for sel in (
        "#onetrust-accept-btn-handler",
        "button#onetrust-accept-btn-handler",
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('Allow all')",
        "button:has-text('I accept')",
        "button:has-text('Got it')",
        "[data-cky-tag='accept-button']",
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:                                     # noqa: BLE001
            continue


def rendered_get(url, wait_for=None, timeout_ms=25000):
    """Navigate, wait out a challenge if there is one, return the DOM."""
    page = get_context().new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        deadline = time.time() + timeout_ms / 1000
        html = page.content()
        while _still_challenging(html) and time.time() < deadline:
            page.wait_for_timeout(1000)
            html = page.content()
        if wait_for:
            try:
                page.wait_for_selector(wait_for, timeout=timeout_ms)
            except Exception:                                 # noqa: BLE001
                page.wait_for_timeout(2000)
        else:
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:                                 # noqa: BLE001
                page.wait_for_timeout(1500)
        _dismiss_cookies(page)
        if wait_for:
            try:
                page.wait_for_selector(wait_for, timeout=8000)
            except Exception:                                 # noqa: BLE001
                pass
        return page.content()
    finally:
        page.close()
