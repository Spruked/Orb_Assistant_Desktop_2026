"""
ORB MORBs — Micro-ORB Evaluators
ActionMORB  : evaluates the result of a single tool execution
StateMORB   : evaluates the overall desktop/browser state

Both route results through the R-Substrate for philosopher-scored verdicts.
Verdict strings: PASS | WARN | FAIL
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from orb_substrate.r_substrate import get_r_substrate, ConvergenceState


# ──────────────────────────────────────────────
# Verdict container
# ──────────────────────────────────────────────

@dataclass
class MORBVerdict:
    verdict:    str       # PASS | WARN | FAIL
    confidence: float
    reason:     str
    tool:       str       = ""
    timestamp:  float     = field(default_factory=time.time)
    substrate_state: str  = ""

    def is_pass(self) -> bool:
        return self.verdict == "PASS"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verdict":         self.verdict,
            "confidence":      round(self.confidence, 4),
            "reason":          self.reason,
            "tool":            self.tool,
            "substrate_state": self.substrate_state,
            "timestamp":       self.timestamp,
        }


# ──────────────────────────────────────────────
# ActionMORB
# ──────────────────────────────────────────────

class ActionMORB:
    """
    Evaluates whether a single tool execution succeeded.
    Combines:
      1. Direct success flag from ORBResult
      2. R-Substrate signal routing for confidence calibration
    """

    def __init__(self):
        self._substrate = get_r_substrate()
        self._history: List[MORBVerdict] = []

    def evaluate(self, result: Any, tool_name: str) -> MORBVerdict:
        """
        Evaluate an ORBResult (or any result with .success and .content).
        Returns a MORBVerdict.
        """
        success  = getattr(result, "success", False)
        content  = getattr(result, "content", [])
        error    = getattr(result, "error", "")
        has_data = bool(content)

        # Build substrate signal
        signal = {
            "action":           tool_name.replace("orb_", ""),
            "dependencies_met": success,
            "state_valid":      success and has_data,
            "plan_steps":       1,
            "context":          tool_name,
            "target":           error or "ok",
        }

        substrate_verdict = self._substrate.route(signal)

        if not success:
            v = MORBVerdict(
                verdict="FAIL",
                confidence=0.0,
                reason=error or "tool returned success=False",
                tool=tool_name,
                substrate_state=substrate_verdict.state.value,
            )
        elif substrate_verdict.state == ConvergenceState.BLOCKED:
            v = MORBVerdict(
                verdict="FAIL",
                confidence=substrate_verdict.confidence,
                reason=f"substrate blocked: {', '.join(substrate_verdict.warnings)}",
                tool=tool_name,
                substrate_state=substrate_verdict.state.value,
            )
        elif substrate_verdict.confidence < 0.40:
            v = MORBVerdict(
                verdict="WARN",
                confidence=substrate_verdict.confidence,
                reason=f"low substrate confidence: {substrate_verdict.confidence:.2f}",
                tool=tool_name,
                substrate_state=substrate_verdict.state.value,
            )
        else:
            v = MORBVerdict(
                verdict="PASS",
                confidence=substrate_verdict.confidence,
                reason=f"ok — confidence: {substrate_verdict.confidence:.2f}",
                tool=tool_name,
                substrate_state=substrate_verdict.state.value,
            )

        self._history.append(v)
        return v

    def recent_verdicts(self, n: int = 10) -> List[Dict[str, Any]]:
        return [v.as_dict() for v in self._history[-n:]]

    def pass_rate(self) -> float:
        if not self._history:
            return 0.0
        return sum(1 for v in self._history if v.verdict == "PASS") / len(self._history)


# ──────────────────────────────────────────────
# StateMORB
# ──────────────────────────────────────────────

class StateMORB:
    """
    Evaluates global desktop/session state.
    Called after multi-step sequences to assess overall health.
    Tracks: consecutive failures, stale state, browser health.
    """

    def __init__(self):
        self._substrate          = get_r_substrate()
        self._consecutive_fails  = 0
        self._total_actions      = 0
        self._last_state_hash    = ""
        self._session_start      = time.time()

    def update(self, action_verdict: MORBVerdict) -> None:
        """Update state tracking with the latest action verdict."""
        self._total_actions += 1
        if action_verdict.verdict == "FAIL":
            self._consecutive_fails += 1
        else:
            self._consecutive_fails = 0

    def evaluate_session(self) -> MORBVerdict:
        """Evaluate overall session health."""
        session_age = time.time() - self._session_start

        signal = {
            "action":           "session_health",
            "dependencies_met": self._consecutive_fails < 3,
            "state_valid":      self._consecutive_fails == 0,
            "plan_steps":       self._total_actions,
            "context":          "state_morb",
        }

        substrate_verdict = self._substrate.route(signal)

        if self._consecutive_fails >= 5:
            reason  = f"critical: {self._consecutive_fails} consecutive failures"
            verdict = "FAIL"
        elif self._consecutive_fails >= 3:
            reason  = f"warning: {self._consecutive_fails} consecutive failures"
            verdict = "WARN"
        else:
            reason  = (
                f"healthy: {self._total_actions} actions, "
                f"{self._consecutive_fails} consecutive fails"
            )
            verdict = "PASS"

        return MORBVerdict(
            verdict=verdict,
            confidence=substrate_verdict.confidence,
            reason=reason,
            tool="state_morb",
            substrate_state=substrate_verdict.state.value,
        )

    @property
    def consecutive_fails(self) -> int:
        return self._consecutive_fails

    @property
    def total_actions(self) -> int:
        return self._total_actions

    def reset(self) -> None:
        self._consecutive_fails = 0
        self._total_actions     = 0
