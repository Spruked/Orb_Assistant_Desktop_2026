"""
The presence loop must not run a cognition pass (over a second of CPU on this machine) on every poll.

Run from electron/src:   python -B -m unittest test_presence_budget -v
"""

import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

from caleon_presence.core.desktop_presence import DesktopContext, DesktopPresence, SensorConfig  # noqa: E402


def presence():
    p = DesktopPresence.__new__(DesktopPresence)  # no sensors, threads or learner needed
    p.is_idle = False
    p._last_emit_signature = None
    p._last_emit_at = 0.0
    p.orb = SimpleNamespace(cognitively_emerge=lambda stimulus: calls.append(stimulus))
    return p


calls = []


def context(**overrides):
    base = dict(timestamp=time.time(), cursor_x=10, cursor_y=20, active_window="Code", active_process="Code.exe",
                browser_domain=None, system_load=12.0, memory_usage=55.0, quadrant="TOP_LEFT", idle_seconds=0,
                cursor_velocity_bucket="still", transition_type=None)
    base.update(overrides)
    return DesktopContext(**base)


class PresenceGateTests(unittest.TestCase):
    def setUp(self):
        calls.clear()

    def test_the_first_context_is_emitted(self):
        self.assertTrue(presence()._should_emit_context(context()))

    def test_an_unchanged_desktop_is_not_emitted_again(self):
        p = presence()
        self.assertTrue(p._should_emit_context(context()))
        for _ in range(20):
            self.assertFalse(p._should_emit_context(context()))

    def test_values_that_change_every_poll_do_not_count_as_a_change(self):
        p = presence()
        p._should_emit_context(context())
        noisy = context(system_load=87.5, memory_usage=61.2, idle_seconds=14, cursor_x=900, cursor_y=400)
        self.assertFalse(p._should_emit_context(noisy))

    def test_real_changes_are_emitted(self):
        p = presence()
        p._should_emit_context(context())
        for change in (
            dict(active_window="Excel"), dict(active_process="chrome.exe"), dict(browser_domain="spruked.com"),
            dict(quadrant="BOTTOM_RIGHT"), dict(cursor_velocity_bucket="fast"), dict(transition_type="window"),
        ):
            with self.subTest(change=change):
                self.assertTrue(p._should_emit_context(context(**change)))
                self.assertTrue(p._should_emit_context(context()))  # and back again counts as a change too

    def test_going_idle_is_a_change(self):
        p = presence()
        p._should_emit_context(context())
        p.is_idle = True
        self.assertTrue(p._should_emit_context(context()))

    def test_a_quiet_desktop_still_gets_a_heartbeat(self):
        p = presence()
        p._should_emit_context(context())
        p._last_emit_at -= SensorConfig.CONTEXT_EMIT_HEARTBEAT_S + 1
        self.assertTrue(p._should_emit_context(context()))
        self.assertFalse(p._should_emit_context(context()))

    def test_heartbeat_is_slow_enough_to_matter(self):
        self.assertGreaterEqual(SensorConfig.CONTEXT_EMIT_HEARTBEAT_S, 15)
        # the context loop polls every 2.8 s; without the gate that was 10+ cognition passes per 30 s
        polls = int(SensorConfig.CONTEXT_EMIT_HEARTBEAT_S * 1000 / SensorConfig.CONTEXT_INTERVAL_MS)
        p = presence()
        emitted = 0
        for _ in range(polls):
            emitted += p._should_emit_context(context())
        self.assertEqual(emitted, 1)


if __name__ == "__main__":
    unittest.main()
