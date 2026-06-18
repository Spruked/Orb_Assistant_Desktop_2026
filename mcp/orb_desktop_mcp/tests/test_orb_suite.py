"""
ORB Desktop MCP — Test Suite
Tests all internal modules without requiring pyautogui, playwright, or a display.
Run: pytest tests/ -v
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ──────────────────────────────────────────────
# R-Substrate Tests
# ──────────────────────────────────────────────

class TestRSubstrate:
    def setup_method(self):
        from orb_substrate.r_substrate import RSubstrate
        self.sub = RSubstrate()

    def test_all_nodes_fire(self):
        signal = {
            "action": "click",
            "target": "button",
            "coordinates": {"x": 100, "y": 200},
            "args": {"x": 100, "y": 200},
            "plan_steps": 1,
            "dependencies_met": True,
            "state_valid": True,
            "context": "click button",
        }
        verdict = self.sub.route(signal)
        assert verdict.ecm.all_nodes_fired, "All four philosopher nodes must fire"

    def test_blocked_on_safety_flag(self):
        signal = {
            "action": "delete",
            "safety_flag": True,
            "target": "",
            "coordinates": {},
            "args": {},
            "plan_steps": 1,
            "dependencies_met": True,
            "state_valid": True,
            "context": "delete",
        }
        verdict = self.sub.route(signal)
        from orb_substrate.r_substrate import ConvergenceState
        assert verdict.ecm.kant_score == 0.0, "Kant must block on safety_flag"
        assert verdict.state == ConvergenceState.BLOCKED

    def test_converged_on_valid_click(self):
        signal = {
            "action": "click",
            "target": "ok",
            "coordinates": {"x": 500, "y": 300},
            "args": {"x": 500, "y": 300, "button": "left"},
            "plan_steps": 1,
            "dependencies_met": True,
            "state_valid": True,
            "context": "click ok button",
        }
        verdict = self.sub.route(signal)
        assert verdict.confidence > 0.5, f"Expected confidence > 0.5, got {verdict.confidence}"

    def test_hlsf_magnitude(self):
        from orb_substrate.r_substrate import HLSFVector
        v = HLSFVector(axis_1=0.8, axis_2=0.7, axis_3=0.9)
        assert round(v.magnitude, 2) == round((0.8 * 0.7 * 0.9) ** (1/3), 2)

    def test_round_trip_speed(self):
        """Substrate should resolve in < 50ms deterministically."""
        import time
        signal = {
            "action": "screenshot",
            "target": "",
            "coordinates": {},
            "args": {},
            "plan_steps": 1,
            "dependencies_met": True,
            "state_valid": True,
            "context": "screenshot",
        }
        start = time.perf_counter()
        self.sub.route(signal)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 50, f"Substrate too slow: {elapsed_ms:.1f}ms"

    def test_verdict_log(self):
        signal = {
            "action": "wait",
            "target": "",
            "coordinates": {},
            "args": {"seconds": 1},
            "plan_steps": 1,
            "dependencies_met": True,
            "state_valid": True,
            "context": "wait 1 second",
        }
        self.sub.route(signal)
        log = self.sub.verdict_log()
        assert len(log) >= 1
        assert "confidence" in log[-1]


# ──────────────────────────────────────────────
# TPC Core Tests
# ──────────────────────────────────────────────

class TestTPCCore:
    def setup_method(self):
        from orb_cognition.tpc_core import TPCCore
        self.tpc = TPCCore()

    def test_parse_click_with_coords(self):
        intent = self.tpc.parse_intent("click at 500 300")
        assert intent.action == "click"
        assert intent.coordinates == {"x": 500, "y": 300}

    def test_parse_type_with_quotes(self):
        intent = self.tpc.parse_intent('type "hello world"')
        assert intent.action == "type"
        assert intent.parameters.get("text") == "hello world"

    def test_parse_navigate_url(self):
        intent = self.tpc.parse_intent("navigate to example.com")
        assert intent.action == "navigate"
        assert "example.com" in intent.parameters.get("url", "")

    def test_parse_scroll_direction(self):
        intent = self.tpc.parse_intent("scroll down 3")
        assert intent.action == "scroll"
        assert intent.parameters.get("direction") == "down"
        assert intent.parameters.get("amount") == 3

    def test_parse_screenshot(self):
        intent = self.tpc.parse_intent("take a screenshot")
        assert intent.action == "screenshot"

    def test_parse_wait(self):
        intent = self.tpc.parse_intent("wait 5 seconds")
        assert intent.action == "wait"
        assert intent.parameters.get("seconds") == 5.0

    def test_unknown_command_requires_clarification(self):
        intent = self.tpc.parse_intent("xyzzy frobnicate the quux")
        assert intent.requires_clarification or intent.confidence < 0.5

    def test_generate_plan_click(self):
        intent = self.tpc.parse_intent("click at 100 200")
        plan   = self.tpc.generate_plan(intent)
        assert len(plan.steps) >= 1
        assert plan.steps[0]["tool"] == "orb_click"

    def test_generate_plan_navigate_has_browser_open(self):
        intent = self.tpc.parse_intent("navigate to google.com")
        plan   = self.tpc.generate_plan(intent)
        tools  = [s["tool"] for s in plan.steps]
        assert "orb_browser_open" in tools
        assert "orb_browser_navigate" in tools

    def test_reconcile_all_pass(self):
        intent = self.tpc.parse_intent("screenshot")
        plan   = self.tpc.generate_plan(intent)
        mock_verdicts = [type("V", (), {"verdict": "PASS", "confidence": 0.9, "reason": "ok"})()]
        result = self.tpc.reconcile_execution_result(plan, plan.steps, mock_verdicts)
        assert result["usable"] is True
        assert result["axis_3_calibration"]["recommendation"] in ("PROCEED", "VERIFY")

    def test_reconcile_all_fail(self):
        intent = self.tpc.parse_intent("click at 100 200")
        plan   = self.tpc.generate_plan(intent)
        mock_verdicts = [type("V", (), {"verdict": "FAIL", "confidence": 0.0, "reason": "error"})()]
        result = self.tpc.reconcile_execution_result(plan, plan.steps, mock_verdicts)
        assert result["usable"] is False


# ──────────────────────────────────────────────
# Safety Guard Tests
# ──────────────────────────────────────────────

class TestSafetyGuard:
    def setup_method(self):
        from orb_safety.safety_guard import ORBSafetyGuard
        self.guard = ORBSafetyGuard()

    def test_allow_normal_click(self):
        allowed, reason = self.guard.evaluate("orb_click", {"x": 500, "y": 300})
        assert allowed

    def test_block_out_of_bounds(self):
        allowed, reason = self.guard.evaluate("orb_click", {"x": -100, "y": 300})
        assert not allowed
        assert "coordinate_bounds" in reason

    def test_block_destructive_type(self):
        allowed, reason = self.guard.evaluate("orb_type", {"text": "rm -rf /home/user"})
        assert not allowed

    def test_block_empty_type(self):
        allowed, reason = self.guard.evaluate("orb_type", {"text": ""})
        assert not allowed

    def test_warn_excessive_wait(self):
        allowed, reason = self.guard.evaluate("orb_wait", {"seconds": 60})
        assert allowed  # warn, not block
        assert "WARN" in reason

    def test_block_javascript_url(self):
        allowed, reason = self.guard.evaluate(
            "orb_browser_navigate", {"url": "javascript:alert(1)"}
        )
        assert not allowed

    def test_allow_normal_navigate(self):
        allowed, reason = self.guard.evaluate(
            "orb_browser_navigate", {"url": "https://example.com"}
        )
        assert allowed


# ──────────────────────────────────────────────
# MORB Tests
# ──────────────────────────────────────────────

class TestActionMORB:
    def setup_method(self):
        from orb_morbs.action_morb import ActionMORB
        self.morb = ActionMORB()

    def _make_result(self, success: bool, text: str = "ok", error: str = ""):
        return type("R", (), {
            "success": success,
            "content": [{"type": "text", "text": text}],
            "error": error,
        })()

    def test_pass_on_success(self):
        result  = self._make_result(True)
        verdict = self.morb.evaluate(result, "orb_screenshot")
        # Should be PASS or WARN (not FAIL)
        assert verdict.verdict in ("PASS", "WARN")

    def test_fail_on_failure(self):
        result  = self._make_result(False, "error", "click failed")
        verdict = self.morb.evaluate(result, "orb_click")
        assert verdict.verdict == "FAIL"

    def test_pass_rate_tracking(self):
        for _ in range(3):
            self.morb.evaluate(self._make_result(True), "orb_click")
        self.morb.evaluate(self._make_result(False), "orb_click")
        rate = self.morb.pass_rate()
        assert 0.0 < rate <= 1.0


class TestStateMORB:
    def setup_method(self):
        from orb_morbs.action_morb import StateMORB, MORBVerdict
        self.morb = StateMORB()
        self.MV   = MORBVerdict

    def test_healthy_session(self):
        v = self.MV("PASS", 0.9, "ok", "orb_click")
        self.morb.update(v)
        session = self.morb.evaluate_session()
        assert session.verdict in ("PASS", "WARN")

    def test_critical_on_many_fails(self):
        v = self.MV("FAIL", 0.0, "err", "orb_click")
        for _ in range(6):
            self.morb.update(v)
        session = self.morb.evaluate_session()
        assert session.verdict == "FAIL"
        assert self.morb.consecutive_fails >= 5


# ──────────────────────────────────────────────
# MCP Bridge Tests
# ──────────────────────────────────────────────

class TestMCPBridge:
    def setup_method(self):
        from orb_controller.mcp_bridge import ORBMCPBridge
        self.bridge = ORBMCPBridge()
        self.bridge.start()

    def test_starts_active(self):
        assert self.bridge.active

    def test_records_call(self):
        result = {"content": [{"type": "text", "text": "ok"}], "isError": False}
        self.bridge.wrap_call("orb_click", result, 5.0)
        summary = self.bridge.session.summary()
        assert summary["total_calls"] == 1
        assert summary["success_rate"] == 1.0

    def test_records_error(self):
        result = {"content": [{"type": "text", "text": "err"}], "isError": True}
        self.bridge.wrap_call("orb_click", result, 2.0)
        summary = self.bridge.session.summary()
        assert summary["error_counts"].get("orb_click", 0) == 1

    def test_capabilities(self):
        caps = self.bridge.capabilities()
        assert caps["tpc_reasoning"]
        assert caps["r_substrate"]
        assert caps["llm_optional"]
