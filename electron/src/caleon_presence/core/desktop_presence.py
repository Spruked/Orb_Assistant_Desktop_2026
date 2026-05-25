# Caleon desktop presence integration for Orb runtime (headless + deterministic).

import ctypes
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None

try:
    import pyautogui  # type: ignore

    pyautogui.FAILSAFE = True
except Exception:  # pragma: no cover - optional dependency
    pyautogui = None

try:
    import win32gui  # type: ignore
    import win32process  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    win32gui = None
    win32process = None

from .memory_learner import SystemBehaviorLearner


class SensorConfig:
    CONTEXT_INTERVAL_MS = 2800
    IDLE_CHECK_MS = 800
    BROWSER_POLL_S = 2.5
    REFLECTION_INTERVAL_MS = 45000

    HISTORY_MAX_SIZE = 800
    IDLE_THRESHOLD_S = 30

    DEEP_SENSORS_ENABLED = False
    ADAPTIVE_SCALING = True

    EVENT_PRIORITY = {
        "window_focus_change": "HIGH",
        "idle_transition": "HIGH",
        "browser_domain_change": "MEDIUM",
        "cursor_pattern": "LOW",
        "app_launch": "MEDIUM",
        "system_metrics": "LOW",
    }


logger = logging.getLogger("Caleon.Presence")


@dataclass
class DesktopContext:
    timestamp: float
    cursor_x: int
    cursor_y: int
    active_window: str
    active_process: str
    browser_domain: Optional[str] = None
    system_load: float = 0.0
    memory_usage: float = 0.0
    quadrant: str = "UNKNOWN"
    idle_seconds: int = 0
    cursor_velocity_bucket: Optional[str] = None
    transition_type: Optional[str] = None


class BrowserMonitor(threading.Thread):
    """Lightweight browser heartbeat monitor for awareness status."""

    def __init__(self, on_domain_callback, poll_interval_s: float = SensorConfig.BROWSER_POLL_S):
        super().__init__(daemon=True)
        self.on_domain_callback = on_domain_callback
        self.poll_interval_s = max(0.5, float(poll_interval_s))
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            # Reserved for browser integrations.
            self._stop_event.wait(self.poll_interval_s)

    def stop(self):
        self._stop_event.set()
        self.join(timeout=1.5)


class DesktopPresence:
    def __init__(self, orb_controller=None, db_path: str = "vault_system/behavior_learner.db"):
        self.orb = orb_controller
        self.learner = SystemBehaviorLearner(db_path=db_path)
        enabled_raw = os.getenv("ORB_ENABLE_BROWSER_AWARENESS", "1").strip().lower()
        self.browser_awareness_enabled = enabled_raw in {"1", "true", "yes", "on"}
        self.browser_monitor = BrowserMonitor(self._on_browser_domain_change) if self.browser_awareness_enabled else None

        self.current_context: Optional[DesktopContext] = None
        self.last_context: Optional[DesktopContext] = None
        self.last_domain: Optional[str] = None
        self.window_focus_start = time.time()
        self.is_idle = False
        self.idle_seconds = 0
        self.last_input_time = time.time()
        self._last_cursor_pos = None
        self._last_cursor_time = None
        self.last_compaction_time = 0.0

        self._stop_event = threading.Event()
        self._threads = []
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True
        if self.browser_monitor:
            self.browser_monitor.start()
        self._start_loop(self._context_loop, "CaleonPresenceContext")
        self._start_loop(self._idle_loop, "CaleonPresenceIdle")
        self._start_loop(self._reflection_loop, "CaleonPresenceReflect")
        self._capture_context()

    def start_background(self):
        """Explicit non-blocking startup contract for host runtimes."""
        self.start()

    def _start_loop(self, target, name: str):
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        self._threads.append(t)

    def _context_loop(self):
        interval = SensorConfig.CONTEXT_INTERVAL_MS / 1000.0
        while not self._stop_event.is_set():
            self._capture_context()
            self._stop_event.wait(interval)

    def _idle_loop(self):
        interval = SensorConfig.IDLE_CHECK_MS / 1000.0
        while not self._stop_event.is_set():
            self._check_idle_transition()
            self._stop_event.wait(interval)

    def _reflection_loop(self):
        interval = SensorConfig.REFLECTION_INTERVAL_MS / 1000.0
        while not self._stop_event.is_set():
            self._background_reflection()
            self._stop_event.wait(interval)

    def _calculate_quadrant(self, cursor, screen) -> str:
        try:
            x_mid = screen[0] / 2
            y_mid = screen[1] / 2
            if cursor[0] < x_mid and cursor[1] < y_mid:
                return "TOP_LEFT"
            if cursor[0] >= x_mid and cursor[1] < y_mid:
                return "TOP_RIGHT"
            if cursor[0] < x_mid and cursor[1] >= y_mid:
                return "BOTTOM_LEFT"
            return "BOTTOM_RIGHT"
        except Exception:
            return "UNKNOWN"

    def _get_idle_seconds(self) -> int:
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                tick_count = ctypes.windll.kernel32.GetTickCount()
                return max(0, int((tick_count - lii.dwTime) / 1000))
        except Exception:
            pass
        return max(0, int(time.time() - self.last_input_time))

    def _cursor_velocity_bucket(self, cursor: Tuple[int, int], now: float) -> Optional[str]:
        if self._last_cursor_pos is None or self._last_cursor_time is None:
            return None
        dt = max(0.001, now - self._last_cursor_time)
        dx = cursor[0] - self._last_cursor_pos[0]
        dy = cursor[1] - self._last_cursor_pos[1]
        speed = ((dx * dx + dy * dy) ** 0.5) / dt
        if speed < 120:
            return "slow"
        if speed < 600:
            return "medium"
        return "fast"

    def _get_foreground_window(self) -> tuple[str, str]:
        if win32gui is None or win32process is None:
            return ("unknown", "unknown")
        try:
            hwnd = win32gui.GetForegroundWindow()
            window_title = win32gui.GetWindowText(hwnd) or "unknown"
            process_name = "unknown"
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid and psutil is not None:
                    process_name = psutil.Process(pid).name()
            except Exception:
                pass
            return (window_title, process_name)
        except Exception:
            return ("unknown", "unknown")

    def _infer_browser_domain(self, window_title: str, process_name: str) -> Optional[str]:
        if not self.browser_awareness_enabled:
            return None

        process = (process_name or "").lower()
        browser_processes = {
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "brave.exe",
            "opera.exe",
            "vivaldi.exe",
        }
        if process not in browser_processes:
            return None

        title = (window_title or "").lower()
        match = re.search(r"(?:^|\b)((?:[a-z0-9-]+\.)+[a-z]{2,})(?:\b|/)", title)
        if not match:
            return None

        domain = match.group(1).strip(".")
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or None

    def _capture_context(self):
        now = time.time()
        try:
            if pyautogui is not None:
                p = pyautogui.position()
                s = pyautogui.size()
                cursor = (int(p.x), int(p.y))
                screen = (int(s.width), int(s.height))
            else:
                cursor = (0, 0)
                screen = (1920, 1080)

            quadrant = self._calculate_quadrant(cursor, screen)
            velocity_bucket = self._cursor_velocity_bucket(cursor, now)

            if self._last_cursor_pos is None or cursor != self._last_cursor_pos:
                self.last_input_time = now
                self._last_cursor_pos = cursor
                self._last_cursor_time = now

            window_title, process_name = self._get_foreground_window()
            inferred_domain = self._infer_browser_domain(window_title, process_name)
            if inferred_domain and inferred_domain != self.last_domain:
                self._on_browser_domain_change(f"https://{inferred_domain}", window_title)
            load = psutil.cpu_percent(interval=0) if psutil is not None else 0.0
            mem = psutil.virtual_memory().percent if psutil is not None else 0.0

            previous = self.current_context
            context = DesktopContext(
                timestamp=now,
                cursor_x=cursor[0],
                cursor_y=cursor[1],
                active_window=window_title,
                active_process=process_name,
                browser_domain=inferred_domain or self.last_domain,
                system_load=load,
                memory_usage=mem,
                quadrant=quadrant,
                idle_seconds=self.idle_seconds,
                cursor_velocity_bucket=velocity_bucket,
            )

            if previous and previous.active_window != window_title:
                duration = now - self.window_focus_start
                self.learner.record_transition(
                    "window_focus_change",
                    previous.active_window,
                    window_title,
                    duration,
                )
                self.window_focus_start = now
                context.transition_type = "window"

            self.last_context = previous
            self.current_context = context
            self._emit_context(context)
        except Exception as exc:
            logger.debug("Context capture failed: %s", exc)

    def _emit_context(self, context: DesktopContext):
        if not self.orb or not hasattr(self.orb, "cognitively_emerge"):
            return
        stimulus = {
            "type": "desktop_context",
            "intent": "presence_tracking",
            "coordinates": [context.cursor_x, context.cursor_y],
            "velocity": 0.0,
            "meta": {"source": "caleon_presence", "idle_seconds": context.idle_seconds},
            "presence_context": asdict(context),
        }
        try:
            self.orb.cognitively_emerge(stimulus)
        except Exception as exc:
            logger.debug("orb context emit failed: %s", exc)

    def _check_idle_transition(self):
        was_idle = self.is_idle
        self.idle_seconds = self._get_idle_seconds()
        self.is_idle = self.idle_seconds >= SensorConfig.IDLE_THRESHOLD_S

        if self.is_idle != was_idle:
            event = "idle_start" if self.is_idle else "idle_end"
            self.learner.record_transition(event, str(was_idle), str(self.is_idle))
            if self.orb and hasattr(self.orb, "cognitively_emerge"):
                try:
                    self.orb.cognitively_emerge(
                        {
                            "type": "idle_transition",
                            "intent": "presence_tracking",
                            "coordinates": [0, 0],
                            "velocity": 0.0,
                            "meta": {
                                "source": "caleon_presence",
                                "event": event,
                                "idle_seconds": self.idle_seconds,
                            },
                        }
                    )
                except Exception:
                    pass

    def _on_browser_domain_change(self, url: str, title: str):
        domain = self._extract_domain(url)
        if domain and domain != self.last_domain:
            self.learner.record_transition(
                "browser_domain_change",
                self.last_domain or "none",
                domain,
            )
            self.last_domain = domain

    def _extract_domain(self, url: str) -> Optional[str]:
        if not url or url == "unknown":
            return None
        try:
            from urllib.parse import urlparse

            return urlparse(url).netloc or None
        except Exception:
            return None

    def _get_recent_high_priority_events(self, since_seconds: int = 7 * 86400, limit: int = 200):
        try:
            now = time.time()
            since = now - since_seconds
            cur = self.learner.conn.execute(
                "SELECT timestamp, event_type, from_value, to_value, duration, day_of_week, hour_of_day, priority FROM transitions WHERE timestamp>? AND priority IN ('HIGH','MEDIUM') ORDER BY timestamp DESC LIMIT ?",
                (since, limit),
            )
            rows = cur.fetchall()
            keys = [
                "timestamp",
                "event_type",
                "from_value",
                "to_value",
                "duration",
                "day_of_week",
                "hour_of_day",
                "priority",
            ]
            return [dict(zip(keys, r)) for r in rows]
        except Exception:
            return []

    def _background_reflection(self):
        if not self.is_idle:
            return

        now = time.time()
        if now - self.last_compaction_time < 300:
            return

        try:
            self.learner.apply_decay()
            self.learner.promote_patterns()
            self.learner.resolve_contradictions()
        except Exception:
            pass
        self.last_compaction_time = now

        truth = []
        try:
            truth = self.learner.get_vault_truth(min_confidence=0.75)
        except Exception:
            pass

        stimulus = {
            "type": "idle_reflection",
            "intent": "reflection",
            "coordinates": [0, 0],
            "velocity": 0.0,
            "meta": {"source": "caleon_presence"},
            "truth_snapshot": truth,
            "recent_events": self._get_recent_high_priority_events(),
        }

        if not self.orb:
            return
        try:
            if hasattr(self.orb, "idle_cognition"):
                self.orb.idle_cognition(stimulus)
            elif hasattr(self.orb, "cognitively_emerge"):
                self.orb.cognitively_emerge(stimulus)
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "is_idle": self.is_idle,
            "idle_seconds": self.idle_seconds,
            "last_domain": self.last_domain,
            "has_context": self.current_context is not None,
            "browser_awareness": {
                "enabled": self.browser_awareness_enabled,
                "running": bool(self.browser_monitor and self.browser_monitor.is_alive()),
                "source": "active_window_inference",
            },
        }

    def stop(self):
        self._stop_event.set()
        self.running = False
        try:
            if self.browser_monitor:
                self.browser_monitor.stop()
        except Exception:
            pass
        for t in self._threads:
            try:
                t.join(timeout=1.5)
            except Exception:
                pass
        self._threads = []
        try:
            self.learner.shutdown()
        except Exception:
            pass

    def graceful_shutdown(self):
        self.stop()

    def run(self):
        self.start()
        while self.running and not self._stop_event.wait(0.25):
            pass


def launch_desktop_presence(orb_controller=None):
    presence = DesktopPresence(orb_controller)
    presence.run()
