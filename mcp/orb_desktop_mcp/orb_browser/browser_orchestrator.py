"""
ORB Local Browser Orchestrator
Wraps Playwright (async) for local browser control.
Falls back to pyautogui screen-coordinate injection if Playwright unavailable.
"""

from __future__ import annotations
import asyncio
import base64
import io
from typing import Optional, Any


class ORBLocalBrowser:
    """
    Playwright-backed local browser controller.
    Supports Chrome, Firefox, WebKit.

    Lazy-initialises Playwright on first call — ORB server
    stays running even if Playwright isn't installed.
    """

    def __init__(self, browser: str = "chrome"):
        self._browser_type = browser.lower()
        self._playwright   = None
        self._browser_obj  = None
        self._page         = None
        self._ready        = False

    # ── Lifecycle ──────────────────────────────────────

    def open(self) -> bool:
        """Synchronous wrapper — runs async open in a fresh event loop."""
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self._async_open())
            loop.close()
            return result
        except Exception as e:
            print(f"[ORBBrowser] open error: {e}")
            return False

    async def _async_open(self) -> bool:
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            launcher = {
                "chrome":   self._playwright.chromium,
                "chromium": self._playwright.chromium,
                "firefox":  self._playwright.firefox,
                "webkit":   self._playwright.webkit,
                "safari":   self._playwright.webkit,
            }.get(self._browser_type, self._playwright.chromium)

            self._browser_obj = await launcher.launch(headless=False)
            self._page        = await self._browser_obj.new_page()
            self._ready       = True
            return True
        except ImportError:
            print("[ORBBrowser] playwright not installed. Run: pip install playwright && playwright install")
            return False
        except Exception as e:
            print(f"[ORBBrowser] _async_open error: {e}")
            return False

    def close(self) -> None:
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._async_close())
            loop.close()
        except Exception:
            pass

    async def _async_close(self):
        if self._browser_obj:
            await self._browser_obj.close()
        if self._playwright:
            await self._playwright.stop()
        self._ready = False

    # ── Navigation ─────────────────────────────────────

    def navigate(self, url: str) -> bool:
        if not self._ready:
            return False
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self._page.goto(url, timeout=15000))
            loop.close()
            return True
        except Exception as e:
            print(f"[ORBBrowser] navigate error: {e}")
            return False

    def get_url(self) -> str:
        if not self._ready or not self._page:
            return ""
        return self._page.url

    def get_title(self) -> str:
        if not self._ready or not self._page:
            return ""
        try:
            loop = asyncio.new_event_loop()
            title = loop.run_until_complete(self._page.title())
            loop.close()
            return title
        except Exception:
            return ""

    # ── Interaction ────────────────────────────────────

    def click_at(self, x: int, y: int) -> bool:
        if not self._ready:
            return False
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._page.mouse.click(x, y))
            loop.close()
            return True
        except Exception as e:
            print(f"[ORBBrowser] click error: {e}")
            return False

    def click_selector(self, selector: str) -> bool:
        if not self._ready:
            return False
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._page.click(selector, timeout=5000))
            loop.close()
            return True
        except Exception as e:
            print(f"[ORBBrowser] click_selector error: {e}")
            return False

    def type_text(self, text: str, press_enter: bool = False) -> None:
        if not self._ready:
            return
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._page.keyboard.type(text))
            if press_enter:
                loop.run_until_complete(self._page.keyboard.press("Enter"))
            loop.close()
        except Exception as e:
            print(f"[ORBBrowser] type_text error: {e}")

    def scroll_page(self, direction: str = "down", amount: int = 5) -> None:
        if not self._ready:
            return
        delta = amount * 100
        js = (
            f"window.scrollBy(0, {delta})"  if direction == "down"  else
            f"window.scrollBy(0, -{delta})" if direction == "up"    else
            f"window.scrollBy({delta}, 0)"  if direction == "right" else
            f"window.scrollBy(-{delta}, 0)"
        )
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._page.evaluate(js))
            loop.close()
        except Exception as e:
            print(f"[ORBBrowser] scroll error: {e}")

    def fill_field(self, selector: str, text: str) -> bool:
        if not self._ready:
            return False
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._page.fill(selector, text, timeout=5000))
            loop.close()
            return True
        except Exception as e:
            print(f"[ORBBrowser] fill_field error: {e}")
            return False

    # ── Screenshot ─────────────────────────────────────

    def screenshot(self, width: int = 1024) -> Optional[str]:
        """Returns base64-encoded JPEG or None."""
        if not self._ready:
            return None
        try:
            loop = asyncio.new_event_loop()
            raw = loop.run_until_complete(self._page.screenshot(type="jpeg", quality=85))
            loop.close()
            return base64.b64encode(raw).decode()
        except Exception as e:
            print(f"[ORBBrowser] screenshot error: {e}")
            return None

    # ── DOM / JS ──────────────────────────────────────

    def evaluate_js(self, js: str) -> Any:
        if not self._ready:
            return None
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self._page.evaluate(js))
            loop.close()
            return result
        except Exception as e:
            print(f"[ORBBrowser] evaluate_js error: {e}")
            return None

    def get_text_content(self, selector: str) -> str:
        if not self._ready:
            return ""
        try:
            loop = asyncio.new_event_loop()
            text = loop.run_until_complete(
                self._page.inner_text(selector, timeout=5000)
            )
            loop.close()
            return text
        except Exception as e:
            return ""

    def wait_for_selector(self, selector: str, timeout: int = 5000) -> bool:
        if not self._ready:
            return False
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                self._page.wait_for_selector(selector, timeout=timeout)
            )
            loop.close()
            return True
        except Exception:
            return False

    @property
    def is_ready(self) -> bool:
        return self._ready
