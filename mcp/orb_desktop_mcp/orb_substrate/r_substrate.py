"""
ORB R-Substrate — Sovereign Cognitive Foundation
Four-Beam Philosopher Architecture: Locke / Hume / Kant / Spinoza
These nodes predate modern ideological categories — no contemporary bias introduced.

Architecture:
  Input Trinity    → Locke  (empirical grounding, what is observable/provable)
  Reasoning Trinity → Hume  (causal skepticism, pattern from experience)
                    + Kant  (categorical imperatives, rule universalization)
  Resolution Trinity → Spinoza (deterministic cause-and-effect, geometric necessity)

ECM (Epistemic Convergence Matrix) aggregates all four beams into a single
confidence-weighted verdict. HLSF (Harmonic Logic Spatial Frame) provides
the 3-axis geometric engine for spatial reasoning about execution state.
"""

from __future__ import annotations
import math
import time
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


# ──────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────

class PhilosopherID(str, Enum):
    LOCKE   = "locke"
    HUME    = "hume"
    KANT    = "kant"
    SPINOZA = "spinoza"


class ConvergenceState(str, Enum):
    CONVERGED   = "CONVERGED"
    PARTIAL     = "PARTIAL"
    DIVERGED    = "DIVERGED"
    BLOCKED     = "BLOCKED"


# ──────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────

@dataclass
class HLSFVector:
    """
    Harmonic Logic Spatial Frame — three-axis geometric state.
    axis_1: Input integrity  (0.0–1.0)
    axis_2: Reasoning coherence (0.0–1.0)
    axis_3: Resolution confidence (0.0–1.0)
    magnitude: geometric mean of all three axes
    """
    axis_1: float = 0.0   # Input integrity
    axis_2: float = 0.0   # Reasoning coherence
    axis_3: float = 0.0   # Resolution confidence

    @property
    def magnitude(self) -> float:
        """Geometric mean of all three axes."""
        return (self.axis_1 * self.axis_2 * self.axis_3) ** (1 / 3)

    @property
    def euclidean(self) -> float:
        return math.sqrt(self.axis_1 ** 2 + self.axis_2 ** 2 + self.axis_3 ** 2)

    def as_dict(self) -> Dict[str, float]:
        return {
            "axis_1_input":      round(self.axis_1, 4),
            "axis_2_reasoning":  round(self.axis_2, 4),
            "axis_3_resolution": round(self.axis_3, 4),
            "magnitude":         round(self.magnitude, 4),
            "euclidean":         round(self.euclidean, 4),
        }


@dataclass
class PhilosopherNode:
    """
    Sovereign philosopher reasoning node.
    Each node scores a query along its philosophical axis.
    """
    node_id: PhilosopherID
    weight: float = 1.0
    _fired: bool = False
    _last_score: float = 0.0
    _last_reason: str = ""

    def evaluate(self, signal: Dict[str, Any]) -> Tuple[float, str]:
        """
        Evaluate signal through this philosopher's lens.
        Returns (confidence_score 0.0–1.0, reasoning_string).
        """
        self._fired = True

        if self.node_id == PhilosopherID.LOCKE:
            return self._locke_evaluate(signal)
        elif self.node_id == PhilosopherID.HUME:
            return self._hume_evaluate(signal)
        elif self.node_id == PhilosopherID.KANT:
            return self._kant_evaluate(signal)
        elif self.node_id == PhilosopherID.SPINOZA:
            return self._spinoza_evaluate(signal)

        return 0.5, "unknown node"

    # ── Locke: empirical grounding ──────────────────────
    def _locke_evaluate(self, signal: Dict[str, Any]) -> Tuple[float, str]:
        """
        John Locke: tabula rasa, sense data, empirical evidence.
        Scores: Is the input grounded in observable, provable data?
        """
        has_action   = bool(signal.get("action"))
        has_target   = bool(signal.get("target") or signal.get("coordinates"))
        has_context  = bool(signal.get("context") or signal.get("raw_input"))
        completeness = sum([has_action, has_target, has_context]) / 3.0

        # Bonus if coordinates are numerically valid
        coords = signal.get("coordinates", {})
        coord_valid = (
            isinstance(coords.get("x"), (int, float)) and
            isinstance(coords.get("y"), (int, float))
        ) if coords else False

        score = completeness * 0.7 + (0.3 if coord_valid else 0.0)
        reason = (
            f"input_complete={completeness:.2f}, "
            f"coords_valid={coord_valid}"
        )
        self._last_score = score
        self._last_reason = reason
        return score, reason

    # ── Hume: causal skepticism ──────────────────────────
    def _hume_evaluate(self, signal: Dict[str, Any]) -> Tuple[float, str]:
        """
        David Hume: causation from experience, pattern recognition.
        Scores: Does the action have a plausible causal chain?
        """
        action = signal.get("action", "").lower()
        known_causal_actions = {
            "click": 0.9, "type": 0.9, "scroll": 0.85,
            "navigate": 0.8, "open": 0.8, "move": 0.75,
            "screenshot": 0.95, "wait": 0.95, "snapshot": 0.9,
            "read_clipboard": 0.9, "write_clipboard": 0.85,
        }
        base = known_causal_actions.get(action, 0.4)

        # Penalise if action contradicts its own parameters
        args = signal.get("args", {})
        contradictions = 0
        if action == "click" and not (args.get("x") or signal.get("coordinates")):
            contradictions += 1
        if action == "type" and not args.get("text"):
            contradictions += 1
        if action == "navigate" and not args.get("url"):
            contradictions += 1

        penalty = contradictions * 0.15
        score = max(0.0, base - penalty)
        reason = f"action_plausibility={base:.2f}, contradictions={contradictions}"
        self._last_score = score
        self._last_reason = reason
        return score, reason

    # ── Kant: categorical imperative ───────────────────
    def _kant_evaluate(self, signal: Dict[str, Any]) -> Tuple[float, str]:
        """
        Immanuel Kant: categorical imperative, universalizability, duty.
        Scores: Is this action universally applicable / ethically consistent?
        """
        action = signal.get("action", "").lower()
        safety_flag = signal.get("safety_flag", False)

        # Actions with destructive potential get a duty-penalty
        destructive = {"delete", "format", "wipe", "rm", "kill", "terminate"}
        duty_penalty = 0.3 if action in destructive else 0.0

        # If safety has already flagged it, Kant blocks
        if safety_flag:
            score = 0.0
            reason = "safety_flagged: categorical block"
        else:
            score = max(0.1, 1.0 - duty_penalty)
            reason = f"duty_penalty={duty_penalty:.2f}"

        self._last_score = score
        self._last_reason = reason
        return score, reason

    # ── Spinoza: geometric determinism ─────────────────
    def _spinoza_evaluate(self, signal: Dict[str, Any]) -> Tuple[float, str]:
        """
        Baruch Spinoza: deterministic cause-and-effect, geometric necessity.
        Scores: Is the execution chain logically deterministic from first principles?
        """
        plan_steps   = signal.get("plan_steps", 0)
        dependencies = signal.get("dependencies_met", True)
        state_valid  = signal.get("state_valid", True)

        if not dependencies:
            score = 0.2
            reason = "unmet dependencies: chain broken"
        elif not state_valid:
            score = 0.3
            reason = "state invalid: determinism compromised"
        else:
            # More steps = slightly lower confidence (complexity risk)
            complexity_penalty = min(0.3, plan_steps * 0.03)
            score = max(0.5, 1.0 - complexity_penalty)
            reason = f"steps={plan_steps}, complexity_penalty={complexity_penalty:.2f}"

        self._last_score = score
        self._last_reason = reason
        return score, reason


@dataclass
class ECMMatrix:
    """
    Epistemic Convergence Matrix.
    Aggregates all four philosopher node scores into a weighted convergence.
    """
    locke_score:   float = 0.0
    hume_score:    float = 0.0
    kant_score:    float = 0.0
    spinoza_score: float = 0.0

    # Node weights (tuned empirically for desktop automation domain)
    WEIGHTS = {
        PhilosopherID.LOCKE:   0.30,
        PhilosopherID.HUME:    0.25,
        PhilosopherID.KANT:    0.20,
        PhilosopherID.SPINOZA: 0.25,
    }

    @property
    def weighted_confidence(self) -> float:
        return (
            self.locke_score   * self.WEIGHTS[PhilosopherID.LOCKE]   +
            self.hume_score    * self.WEIGHTS[PhilosopherID.HUME]    +
            self.kant_score    * self.WEIGHTS[PhilosopherID.KANT]    +
            self.spinoza_score * self.WEIGHTS[PhilosopherID.SPINOZA]
        )

    @property
    def convergence_state(self) -> ConvergenceState:
        scores = [self.locke_score, self.hume_score, self.kant_score, self.spinoza_score]
        wc = self.weighted_confidence
        variance = sum((s - wc) ** 2 for s in scores) / len(scores)

        if any(s == 0.0 for s in scores):
            return ConvergenceState.BLOCKED
        if wc >= 0.65 and variance < 0.05:
            return ConvergenceState.CONVERGED
        if wc >= 0.40:
            return ConvergenceState.PARTIAL
        return ConvergenceState.DIVERGED

    @property
    def all_nodes_fired(self) -> bool:
        return all(s > 0.0 for s in [
            self.locke_score, self.hume_score, self.kant_score, self.spinoza_score
        ])

    def as_dict(self) -> Dict[str, Any]:
        return {
            "locke":               round(self.locke_score, 4),
            "hume":                round(self.hume_score, 4),
            "kant":                round(self.kant_score, 4),
            "spinoza":             round(self.spinoza_score, 4),
            "weighted_confidence": round(self.weighted_confidence, 4),
            "convergence_state":   self.convergence_state.value,
            "all_nodes_fired":     self.all_nodes_fired,
        }


@dataclass
class SubstrateVerdict:
    """Final verdict produced by R-Substrate after full philosopher pass."""
    ecm:           ECMMatrix
    hlsf:          HLSFVector
    state:         ConvergenceState
    confidence:    float
    timestamp:     float = field(default_factory=time.time)
    signal_hash:   str = ""
    routed:        bool = False
    warnings:      List[str] = field(default_factory=list)
    node_reasons:  Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "routed":       self.routed,
            "state":        self.state.value,
            "confidence":   round(self.confidence, 4),
            "ecm":          self.ecm.as_dict(),
            "hlsf":         self.hlsf.as_dict(),
            "signal_hash":  self.signal_hash,
            "timestamp":    self.timestamp,
            "warnings":     self.warnings,
            "node_reasons": self.node_reasons,
        }


# ──────────────────────────────────────────────
# Core Substrate Engine
# ──────────────────────────────────────────────

class RSubstrate:
    """
    Sovereign cognitive substrate.
    Wires all four philosopher nodes through ECM and HLSF.
    Produces a SubstrateVerdict for every signal routed through it.

    CRITICAL ARCHITECTURAL RULE:
    ORB cognition (TPC) is the primary reasoning layer.
    The LLM is an OPTIONAL articulation layer only.
    This substrate must never receive governance doctrine.
    """

    _instance: Optional["RSubstrate"] = None

    def __init__(self):
        self._nodes = {
            PhilosopherID.LOCKE:   PhilosopherNode(PhilosopherID.LOCKE,   weight=0.30),
            PhilosopherID.HUME:    PhilosopherNode(PhilosopherID.HUME,    weight=0.25),
            PhilosopherID.KANT:    PhilosopherNode(PhilosopherID.KANT,    weight=0.20),
            PhilosopherID.SPINOZA: PhilosopherNode(PhilosopherID.SPINOZA, weight=0.25),
        }
        self._verdict_log: List[SubstrateVerdict] = []
        self._round_trip_ms: float = 0.0

    @classmethod
    def instance(cls) -> "RSubstrate":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def route(self, signal: Dict[str, Any]) -> SubstrateVerdict:
        """
        Route a signal through all four philosopher nodes.
        Returns a fully populated SubstrateVerdict.
        Typical round-trip: ~1.4ms deterministic (no I/O).
        """
        t_start = time.perf_counter()

        # Hash the signal for deduplication / audit trail
        sig_hash = hashlib.sha256(
            json.dumps(signal, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        # ── Fire all four nodes ───────────────────────────
        locke_score,   locke_reason   = self._nodes[PhilosopherID.LOCKE].evaluate(signal)
        hume_score,    hume_reason    = self._nodes[PhilosopherID.HUME].evaluate(signal)
        kant_score,    kant_reason    = self._nodes[PhilosopherID.KANT].evaluate(signal)
        spinoza_score, spinoza_reason = self._nodes[PhilosopherID.SPINOZA].evaluate(signal)

        # ── Build ECM ─────────────────────────────────────
        ecm = ECMMatrix(
            locke_score=locke_score,
            hume_score=hume_score,
            kant_score=kant_score,
            spinoza_score=spinoza_score,
        )

        # ── Build HLSF vector ─────────────────────────────
        # axis_1 = Locke (input integrity)
        # axis_2 = (Hume + Kant) / 2 (reasoning coherence)
        # axis_3 = Spinoza (resolution determinism)
        hlsf = HLSFVector(
            axis_1=locke_score,
            axis_2=(hume_score + kant_score) / 2.0,
            axis_3=spinoza_score,
        )

        # ── Compute final confidence ──────────────────────
        confidence = ecm.weighted_confidence
        state      = ecm.convergence_state
        routed     = state != ConvergenceState.BLOCKED

        # ── Collect warnings ─────────────────────────────
        warnings: List[str] = []
        if ecm.kant_score == 0.0:
            warnings.append("kant_blocked: safety or ethical constraint triggered")
        if hlsf.magnitude < 0.3:
            warnings.append("hlsf_low: geometric confidence below threshold")
        if not ecm.all_nodes_fired:
            warnings.append("partial_fire: not all philosopher nodes engaged")

        t_end = time.perf_counter()
        self._round_trip_ms = (t_end - t_start) * 1000

        verdict = SubstrateVerdict(
            ecm=ecm,
            hlsf=hlsf,
            state=state,
            confidence=confidence,
            signal_hash=sig_hash,
            routed=routed,
            warnings=warnings,
            node_reasons={
                "locke":   locke_reason,
                "hume":    hume_reason,
                "kant":    kant_reason,
                "spinoza": spinoza_reason,
            }
        )
        self._verdict_log.append(verdict)
        return verdict

    def last_round_trip_ms(self) -> float:
        return round(self._round_trip_ms, 3)

    def verdict_log(self) -> List[Dict[str, Any]]:
        return [v.as_dict() for v in self._verdict_log[-50:]]

    def reset_log(self):
        self._verdict_log.clear()


# ── Singleton accessor ────────────────────────────────────────────────────────

_substrate_singleton: Optional[RSubstrate] = None

def get_r_substrate() -> RSubstrate:
    global _substrate_singleton
    if _substrate_singleton is None:
        _substrate_singleton = RSubstrate()
    return _substrate_singleton
