"""
Tests for the three-runtime wiring: Motion, Communications, Cognition/Governance.

Run from electron/src:   python -B -m unittest test_runtimes -v
"""

import re
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

from orb_state_machine import CALIStateMachine  # noqa: E402


def machine():
    return CALIStateMachine(checkout_path=SRC.parent)


class MotionRuntimeTests(unittest.TestCase):
    def test_motion_is_unreported_until_the_renderer_reports(self):
        summary = machine().get_runtime_summary()
        self.assertEqual(summary["motion"]["status"], "unreported")
        self.assertIsNone(summary["motion"]["x"])

    def test_renderer_report_becomes_runtime_ground_truth(self):
        sm = machine()
        sm.report_physical_motion(
            {"mode": "patrol", "x": 1052, "y": 575, "monitor_id": 0, "display_count": 2, "docked": False, "speaking_hold": False}
        )
        motion = sm.get_runtime_summary()["motion"]
        self.assertEqual(motion["status"], "ok")
        self.assertEqual((motion["mode"], motion["x"], motion["y"], motion["monitor_id"]), ("patrol", 1052, 575, 0))
        self.assertEqual(motion["source"], "renderer")
        self.assertEqual(sm.get_effective_state("motion")["physical_mode"], "patrol")

    def test_only_whitelisted_fields_are_accepted(self):
        sm = machine()
        self.assertEqual(sm.report_physical_motion({"cmd": "rm -rf", "evil": 1}), {})
        sm.report_physical_motion({"mode": "idle_hover", "cmd": "x"})
        self.assertNotIn("cmd", sm.get_runtime_state("motion"))

    def test_a_silent_renderer_is_reported_stale_not_ok(self):
        sm = machine()
        sm.report_physical_motion({"mode": "patrol", "x": 1, "y": 2})
        time.sleep(0.05)
        self.assertEqual(sm.get_runtime_summary(motion_stale_s=0.01)["motion"]["status"], "stale")

    def test_disabled_motion_is_reported_as_disabled(self):
        sm = machine()
        sm.report_physical_motion({"mode": "patrol"})
        sm.set_desired_state("motion", {"enabled": False}, source="bridge")
        self.assertEqual(sm.get_runtime_summary()["motion"]["status"], "disabled")

    def test_cursor_processing_does_not_claim_the_cursor_as_a_motion_target(self):
        from orb_behavior_runtime import OrbBehaviorRuntime

        sm = machine()
        runtime = OrbBehaviorRuntime.__new__(OrbBehaviorRuntime)
        runtime.orb = SimpleNamespace(_emit=lambda message: None)
        runtime.state_machine = sm
        runtime.cognitively_emerge = lambda stimulus: {"confidence": 0.5}
        runtime.process_cursor_movement(400, 300)
        self.assertEqual(sm.get_motion_state()["target"], "idle")  # not "cursor"
        activity = sm.get_full_state()["activity"]["motion"]
        self.assertEqual(activity["state"], "cursor_processed")
        self.assertEqual(activity["result"], "success")


class IndependenceTests(unittest.TestCase):
    def test_communications_failure_does_not_affect_motion_or_governance(self):
        sm = machine()
        sm.report_physical_motion({"mode": "patrol", "x": 5, "y": 6})
        sm.update_runtime_state("cognition", {"llm_ready": True}, source="probe")
        sm.set_desired_state("listening", {"enabled": True}, source="bridge")
        sm.update_runtime_state("listening", {"mic_available": False, "cp3_ready": False}, source="MicCapture")
        sm.update_runtime_state("voice", {"tts_ready": False}, source="TTSClient")
        summary = sm.get_runtime_summary()
        self.assertEqual(summary["communications"]["status"], "unavailable")
        self.assertEqual(summary["motion"]["status"], "ok")
        self.assertEqual(summary["cognition_governance"]["status"], "ok")

    def test_partial_communications_failure_is_degraded(self):
        sm = machine()
        sm.update_runtime_state("voice", {"tts_ready": True}, source="TTSClient")
        sm.set_desired_state("listening", {"enabled": True}, source="bridge")
        sm.update_runtime_state("listening", {"mic_available": False}, source="MicCapture")
        summary = sm.get_runtime_summary()["communications"]
        self.assertEqual(summary["status"], "degraded")
        self.assertEqual([b["domain"] for b in summary["blocked"]], ["listening"])

    def test_cognition_failure_does_not_affect_motion_or_communications(self):
        sm = machine()
        sm.report_physical_motion({"mode": "patrol"})
        sm.update_runtime_state("voice", {"tts_ready": True}, source="TTSClient")
        sm.update_runtime_state("cognition", {"llm_ready": False, "llm_error": "llama.cpp down"}, source="LLM")
        summary = sm.get_runtime_summary()
        self.assertEqual(summary["cognition_governance"]["status"], "degraded")
        self.assertEqual(summary["motion"]["status"], "ok")
        self.assertEqual(summary["communications"]["status"], "ok")

    def test_every_domain_belongs_to_exactly_one_runtime_except_system(self):
        owned = [d for domains in CALIStateMachine.RUNTIMES.values() for d in domains]
        self.assertEqual(len(owned), len(set(owned)))
        self.assertEqual(set(owned), CALIStateMachine.DOMAINS - {"system"})

    def test_status_and_full_state_expose_the_runtimes(self):
        sm = machine()
        self.assertEqual(set(sm.get_status()["runtimes"]) - {"generated_at"}, set(CALIStateMachine.RUNTIMES))
        self.assertIn("runtimes", sm.get_full_state())


class RouterTests(unittest.TestCase):
    def test_motion_report_updates_the_state_machine_without_command_lifecycle_noise(self):
        from orb_command_router import OrbCommandRouter

        sm = machine()
        router = OrbCommandRouter.__new__(OrbCommandRouter)
        router.orb = SimpleNamespace(_emit=lambda message: None)
        router.state_machine = sm
        router._dispatch_with_lifecycle({"type": "motion_report", "report": {"mode": "docked", "docked": True, "x": 10, "y": 20}})
        motion = sm.get_runtime_summary()["motion"]
        self.assertEqual((motion["mode"], motion["docked"]), ("docked", True))
        self.assertEqual(sm.get_full_state()["commands"]["recent"], [])
        self.assertIn("motion_report", OrbCommandRouter._LIFECYCLE_EXEMPT)


class CommandHistoryTests(unittest.TestCase):
    def test_cursor_samples_do_not_flood_the_command_lifecycle(self):
        from orb_command_router import OrbCommandRouter

        events = []
        sm = machine()
        router = OrbCommandRouter.__new__(OrbCommandRouter)
        router.orb = SimpleNamespace(
            _emit=events.append,
            behavior_runtime=SimpleNamespace(process_cursor_movement=lambda x, y: None),
            lifecycle=SimpleNamespace(get_status=lambda: {}),
        )
        router.state_machine = sm
        for i in range(250):
            router._dispatch_with_lifecycle({"type": "cursor_move", "x": i, "y": i})
        self.assertEqual(events, [])
        self.assertEqual(sm.get_full_state()["commands"]["recent"], [])
        # A real command is still tracked and is not pushed out by cursor samples.
        router._dispatch_with_lifecycle({"type": "get_status", "request_id": "real-1"})
        for i in range(250):
            router._dispatch_with_lifecycle({"type": "cursor_move", "x": i, "y": i})
        self.assertEqual([c["request_id"] for c in sm.get_full_state()["commands"]["recent"]], ["real-1"])
        self.assertIn("cursor_move", OrbCommandRouter._LIFECYCLE_EXEMPT)


class ContractDriftTests(unittest.TestCase):
    """Fails if the renderer, preload, main process and state machine stop agreeing on motion telemetry."""

    @classmethod
    def setUpClass(cls):
        root = SRC.parent
        cls.preload = (root / "main" / "preload.js").read_text(encoding="utf-8")
        cls.main = (root / "main" / "main.js").read_text(encoding="utf-8")
        cls.renderer = (SRC / "orb-renderer.js").read_text(encoding="utf-8")

    def test_preload_exposes_the_report_channel(self):
        self.assertIn("reportMotionState", self.preload)
        self.assertIn("ipcRenderer.send('orb:motion-report'", self.preload)

    def test_main_validates_the_sender_and_forwards_to_python(self):
        block = self.main[self.main.index("ipcMain.on('orb:motion-report'"):]
        block = block[: block.index("\n});") + 4]
        self.assertIn("getOrbWindows().some", block)           # only ORB overlay windows
        self.assertIn("event.sender.id", block)
        self.assertIn("type: 'motion_report'", block)

    def test_main_reports_the_docked_state_when_no_overlay_exists(self):
        self.assertIn("dockedMotionReporter", self.main)
        self.assertIn("report: { mode: 'docked', docked: true }", self.main)

    def test_renderer_actually_calls_the_report_channel(self):
        self.assertIn("reportMotionState?.(", self.renderer)

    def test_report_keys_match_in_main_and_state_machine(self):
        match = re.search(r"const MOTION_REPORT_KEYS = \[(.*?)\];", self.main)
        self.assertIsNotNone(match)
        main_keys = tuple(re.findall(r"'([a-z_]+)'", match.group(1)))
        self.assertEqual(main_keys, CALIStateMachine.MOTION_REPORT_KEYS)
        for key in main_keys:
            self.assertRegex(self.renderer, rf"\b{key}\b")


if __name__ == "__main__":
    unittest.main()
