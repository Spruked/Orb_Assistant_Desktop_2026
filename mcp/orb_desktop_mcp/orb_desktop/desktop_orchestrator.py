"""
ORB Desktop Orchestrator
Cross-platform desktop automation layer.
Uses pyautogui as primary driver with pynput fallback.
All methods return a uniform ORBResult object.
"""

from __future__ import annotations
import time
import base64
import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────
# Result container
# ──────────────────────────────────────────────

@dataclass
class ORBResult:
    success: bool
    content: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @classmethod
    def ok(cls, text: str) -> "ORBResult":
        return cls(success=True, content=[{"type": "text", "text": text}])

    @classmethod
    def image_ok(cls, b64: str, caption: str = "Screenshot") -> "ORBResult":
        return cls(
            success=True,
            content=[
                {"type": "text", "text": caption},
                {"type": "image", "data": b64, "mimeType": "image/jpeg"},
            ]
        )

    @classmethod
    def fail(cls, message: str) -> "ORBResult":
        return cls(success=False, content=[{"type": "text", "text": message}], error=message)


# ──────────────────────────────────────────────
# Desktop Controller
# ──────────────────────────────────────────────

class ORBDesktopController:
    """
    Wraps pyautogui / pynput / PIL.
    Lazy-imports at method call time — ORB will still launch even if
    optional packages are missing; they'll surface clear errors.
    """

    def __init__(self):
        self._pyautogui   = None
        self._screenshot_mod = None
        self._clipboard_mod  = None
        self._ready = False
        self._init()

    def _init(self):
        try:
            import pyautogui
            pyautogui.FAILSAFE      = True
            pyautogui.PAUSE         = 0.05
            self._pyautogui         = pyautogui
            self._ready             = True
        except ImportError:
            pass  # Will surface at call time

    def _require(self) -> None:
        if not self._ready or self._pyautogui is None:
            raise RuntimeError(
                "pyautogui not installed. Run: pip install pyautogui pillow pyperclip"
            )

    # ── Mouse ──────────────────────────────────────────

    def click(self, x: int, y: int, button: str = "left") -> ORBResult:
        try:
            self._require()
            self._pyautogui.click(x, y, button=button)
            return ORBResult.ok(f"Clicked {button} at ({x}, {y})")
        except Exception as e:
            return ORBResult.fail(f"click failed: {e}")

    def double_click(self, x: int, y: int) -> ORBResult:
        try:
            self._require()
            self._pyautogui.doubleClick(x, y)
            return ORBResult.ok(f"Double-clicked at ({x}, {y})")
        except Exception as e:
            return ORBResult.fail(f"double_click failed: {e}")

    def move_mouse(self, x: int, y: int) -> ORBResult:
        try:
            self._require()
            self._pyautogui.moveTo(x, y, duration=0.1)
            return ORBResult.ok(f"Moved mouse to ({x}, {y})")
        except Exception as e:
            return ORBResult.fail(f"move_mouse failed: {e}")

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3) -> ORBResult:
        try:
            self._require()
            self._pyautogui.dragTo(x2, y2, duration=duration, startX=x1, startY=y1)
            return ORBResult.ok(f"Dragged ({x1},{y1}) → ({x2},{y2})")
        except Exception as e:
            return ORBResult.fail(f"drag failed: {e}")

    def scroll(
        self,
        x: int, y: int,
        direction: str = "down",
        amount: int = 5
    ) -> ORBResult:
        try:
            self._require()
            self._pyautogui.moveTo(x, y)
            clicks = amount if direction in ("up", "right") else -amount
            if direction in ("up", "down"):
                self._pyautogui.scroll(clicks)
            else:
                self._pyautogui.hscroll(clicks)
            return ORBResult.ok(f"Scrolled {direction} {amount} at ({x}, {y})")
        except Exception as e:
            return ORBResult.fail(f"scroll failed: {e}")

    # ── Keyboard ───────────────────────────────────────

    def type_text(self, text: str, press_enter: bool = False, interval: float = 0.02) -> ORBResult:
        try:
            self._require()
            self._pyautogui.typewrite(text, interval=interval)
            if press_enter:
                self._pyautogui.press("enter")
            return ORBResult.ok(f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}")
        except Exception as e:
            return ORBResult.fail(f"type_text failed: {e}")

    def hotkey(self, *keys: str) -> ORBResult:
        try:
            self._require()
            self._pyautogui.hotkey(*keys)
            return ORBResult.ok(f"Hotkey: {'+'.join(keys)}")
        except Exception as e:
            return ORBResult.fail(f"hotkey failed: {e}")

    def press_key(self, key: str) -> ORBResult:
        try:
            self._require()
            self._pyautogui.press(key)
            return ORBResult.ok(f"Pressed: {key}")
        except Exception as e:
            return ORBResult.fail(f"press_key failed: {e}")

    # ── Screen ─────────────────────────────────────────

    def screenshot(self, width: int = 1024) -> ORBResult:
        try:
            self._require()
            img = self._pyautogui.screenshot()
            # Resize if needed
            if img.width > width:
                ratio  = width / img.width
                height = int(img.height * ratio)
                img    = img.resize((width, height))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return ORBResult.image_ok(b64, f"Screenshot ({img.width}x{img.height})")
        except Exception as e:
            return ORBResult.fail(f"screenshot failed: {e}")

    def get_display_size(self) -> Tuple[int, int]:
        try:
            self._require()
            return self._pyautogui.size()
        except Exception:
            return (1920, 1080)

    def snapshot(self, use_vision: bool = True) -> Dict[str, Any]:
        """Full desktop snapshot: screenshot + window list."""
        result: Dict[str, Any] = {}
        shot = self.screenshot()
        if shot.success and len(shot.content) > 1:
            result["screenshot_b64"] = shot.content[1]["data"]

        win_result = self.list_windows()
        if win_result.success and win_result.content:
            import json
            try:
                result["windows"] = json.loads(win_result.content[0]["text"])
            except Exception:
                result["windows"] = []

        size = self.get_display_size()
        result["display"] = {"width": size[0], "height": size[1]}
        return result

    # ── Applications ────────────────────────────────────

    def open_app(self, bundle_id: str) -> ORBResult:
        """Open application. Attempts cross-platform strategies."""
        import platform
        import subprocess
        system = platform.system()
        try:
            if system == "Darwin":
                ret = subprocess.run(
                    ["open", "-b", bundle_id],
                    capture_output=True, timeout=5
                )
                if ret.returncode == 0:
                    return ORBResult.ok(f"Opened app: {bundle_id}")
                return ORBResult.fail(f"macOS open failed: {ret.stderr.decode()}")

            elif system == "Windows":
                import subprocess
                # Windows: use start command or explorer
                subprocess.Popen(["explorer.exe", bundle_id])
                return ORBResult.ok(f"Launched: {bundle_id}")

            elif system == "Linux":
                subprocess.Popen(["xdg-open", bundle_id])
                return ORBResult.ok(f"Opened: {bundle_id}")

            return ORBResult.fail(f"Unsupported platform: {system}")
        except Exception as e:
            return ORBResult.fail(f"open_app failed: {e}")

    def list_windows(self) -> ORBResult:
        """List visible windows. Platform-specific."""
        import platform, json
        system = platform.system()
        try:
            if system == "Darwin":
                import subprocess
                script = """
                tell application "System Events"
                    set winList to {}
                    repeat with proc in (processes where background only is false)
                        set end of winList to name of proc
                    end repeat
                    return winList
                end tell
                """
                ret = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True, timeout=5
                )
                if ret.returncode == 0:
                    wins = [w.strip() for w in ret.stdout.strip().split(",")]
                    return ORBResult.ok(json.dumps(wins, indent=2))

            elif system == "Windows":
                import ctypes
                wins = []
                def callback(hwnd, _):
                    if ctypes.windll.user32.IsWindowVisible(hwnd):
                        buf = ctypes.create_unicode_buffer(256)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                        if buf.value:
                            wins.append(buf.value)
                ctypes.windll.user32.EnumWindows(
                    ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)(callback),
                    0
                )
                return ORBResult.ok(json.dumps(wins, indent=2))

        except Exception as e:
            return ORBResult.fail(f"list_windows failed: {e}")

        return ORBResult.ok("[]")

    # ── Clipboard ───────────────────────────────────────

    def read_clipboard(self) -> str:
        try:
            import pyperclip
            return pyperclip.paste()
        except ImportError:
            try:
                import subprocess
                import platform
                if platform.system() == "Darwin":
                    return subprocess.run(
                        ["pbpaste"], capture_output=True, text=True
                    ).stdout
                elif platform.system() == "Windows":
                    return subprocess.run(
                        ["clip"], capture_output=True, text=True
                    ).stdout
            except Exception:
                pass
        return ""

    def write_clipboard(self, text: str) -> None:
        try:
            import pyperclip
            pyperclip.copy(text)
        except ImportError:
            try:
                import subprocess, platform
                if platform.system() == "Darwin":
                    subprocess.run(["pbcopy"], input=text.encode(), check=True)
                elif platform.system() == "Windows":
                    subprocess.run(["clip"], input=text.encode(), check=True)
            except Exception:
                pass

    # ── Utility ─────────────────────────────────────────

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
