"""
TPC Core — Triple Predicate Cubed Reasoning Engine
Three-axis geometric engine:
  Input Trinity     → What is the raw request?
  Reasoning Trinity → What does it mean and what should happen?
  Resolution Trinity → What is the deterministic execution plan?

Every parse flows through the R-Substrate philosopher nodes first.
Confidence is set by the ECM, not by heuristics alone.
"""

from __future__ import annotations
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from orb_substrate.r_substrate import get_r_substrate, ConvergenceState


# ──────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────

@dataclass
class ParsedIntent:
    raw_input: str
    action: str
    target: str
    coordinates: Dict[str, Any]
    parameters: Dict[str, Any]
    confidence: float
    requires_clarification: bool
    substrate_state: str = ""
    signal_hash: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExecutionStep:
    tool: str
    args: Dict[str, Any]
    description: str = ""


@dataclass
class ExecutionPlan:
    steps: List[Dict[str, Any]]
    fallback_steps: List[Dict[str, Any]]
    intent_summary: str
    estimated_confidence: float


# ──────────────────────────────────────────────
# Intent Parser
# ──────────────────────────────────────────────

class TPCIntentParser:
    """
    Input Trinity — axis_1 of TPC.
    Parses raw natural language commands into structured intent.
    All parsing is deterministic regex + pattern matching. No LLM.
    """

    # ── Coordinate extractor ────────────────────────────
    _COORD_RE = re.compile(
        r"(?:at\s+)?(-?\d+)[,\s]+(-?\d+)",
        re.IGNORECASE
    )

    # ── URL extractor ────────────────────────────────────
    _URL_RE = re.compile(
        r"https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?",
        re.IGNORECASE
    )

    # ── Action keyword map ────────────────────────────────
    # Format: keyword → (canonical_action, tool_name)
    ACTION_MAP: Dict[str, Tuple[str, str]] = {
        "click":      ("click",      "orb_click"),
        "tap":        ("click",      "orb_click"),
        "press":      ("click",      "orb_click"),
        "rightclick": ("click",      "orb_click"),
        "right-click":("click",      "orb_click"),
        "type":       ("type",       "orb_type"),
        "write":      ("type",       "orb_type"),
        "enter":      ("type",       "orb_type"),
        "input":      ("type",       "orb_type"),
        "scroll":     ("scroll",     "orb_scroll"),
        "move":       ("move_mouse", "orb_move_mouse"),
        "drag":       ("move_mouse", "orb_move_mouse"),
        "screenshot": ("screenshot", "orb_screenshot"),
        "capture":    ("screenshot", "orb_screenshot"),
        "snap":       ("screenshot", "orb_screenshot"),
        "open":       ("open_app",   "orb_open_app"),
        "launch":     ("open_app",   "orb_open_app"),
        "start":      ("open_app",   "orb_open_app"),
        "navigate":   ("navigate",   "orb_browser_navigate"),
        "go to":      ("navigate",   "orb_browser_navigate"),
        "goto":       ("navigate",   "orb_browser_navigate"),
        "visit":      ("navigate",   "orb_browser_navigate"),
        "browse":     ("navigate",   "orb_browser_navigate"),
        "wait":       ("wait",       "orb_wait"),
        "pause":      ("wait",       "orb_wait"),
        "sleep":      ("wait",       "orb_wait"),
        "snapshot":   ("snapshot",   "orb_snapshot"),
        "read":       ("clipboard_read", "orb_clipboard_read"),
        "paste":      ("clipboard_read", "orb_clipboard_read"),
        "copy":       ("clipboard_write","orb_clipboard_write"),
        "list":       ("list_windows",   "orb_list_windows"),
        "windows":    ("list_windows",   "orb_list_windows"),
    }

    def parse(self, raw: str) -> Tuple[str, str, Dict[str, Any], Dict[str, Any]]:
        """
        Returns (action, target, coordinates, parameters).
        Purely deterministic — no probabilistic elements here.
        Confidence is computed separately by ECM.
        """
        text  = raw.strip().lower()
        words = text.split()

        action   = ""
        target   = ""
        coords   = {}
        params   = {}

        # ── Find action ─────────────────────────────────
        # Multi-word first
        for kw in ["go to", "right-click"]:
            if kw in text:
                action, _ = self.ACTION_MAP[kw]
                text = text.replace(kw, "").strip()
                break

        if not action:
            for word in words:
                if word in self.ACTION_MAP:
                    action = self.ACTION_MAP[word][0]
                    break

        # ── Extract coordinates ──────────────────────────
        m = self._COORD_RE.search(raw)
        if m:
            coords = {"x": int(m.group(1)), "y": int(m.group(2))}

        # ── Extract URL ──────────────────────────────────
        url_m = self._URL_RE.search(raw)
        if url_m:
            url = url_m.group(0)
            if not url.startswith("http"):
                url = "https://" + url
            params["url"] = url
            target = url

        # ── Extract quoted text (for type actions) ───────
        quoted = re.findall(r'"([^"]*)"', raw)
        if not quoted:
            quoted = re.findall(r"'([^']*)'", raw)
        if quoted:
            params["text"] = quoted[0]
            target = quoted[0]

        # ── Extract numbers (wait seconds, scroll amount) ─
        numbers = re.findall(r"\b(\d+(?:\.\d+)?)\b", raw)
        if numbers:
            if action == "wait":
                params["seconds"] = float(numbers[0])
            elif action == "scroll":
                params["amount"] = int(numbers[-1]) if numbers else 5

        # ── Scroll direction ─────────────────────────────
        if action == "scroll":
            if "up" in text:
                params["direction"] = "up"
            elif "down" in text:
                params["direction"] = "down"
            elif "left" in text:
                params["direction"] = "left"
            elif "right" in text:
                params["direction"] = "right"
            else:
                params["direction"] = "down"

        # ── Button for click ─────────────────────────────
        if action == "click":
            if "right" in text:
                params["button"] = "right"
            elif "middle" in text:
                params["button"] = "middle"
            else:
                params["button"] = "left"

        # ── Enter key for type ───────────────────────────
        if action == "type":
            params["press_enter"] = "enter" in text or "submit" in text or "return" in text

        # ── App bundle ID guess ──────────────────────────
        if action == "open_app" and not target:
            BUNDLE_MAP = {
                "chrome":   "com.google.Chrome",
                "firefox":  "org.mozilla.firefox",
                "safari":   "com.apple.Safari",
                "terminal": "com.apple.Terminal",
                "notepad":  "Microsoft.WindowsNotepad",
                "calc":     "Microsoft.WindowsCalculator",
                "vscode":   "com.microsoft.VSCode",
                "finder":   "com.apple.finder",
            }
            for app_name, bundle in BUNDLE_MAP.items():
                if app_name in text:
                    params["bundle_id"] = bundle
                    target = app_name
                    break

        # Merge coords into params for tools that need x/y
        if coords:
            params.update(coords)

        return action, target, coords, params


# ──────────────────────────────────────────────
# Plan Generator
# ──────────────────────────────────────────────

class TPCPlanGenerator:
    """
    Reasoning Trinity + Resolution Trinity — axes 2 and 3 of TPC.
    Converts a ParsedIntent into an ExecutionPlan.
    Fallback steps are generated automatically.
    """

    def generate(self, intent: ParsedIntent) -> ExecutionPlan:
        steps: List[Dict[str, Any]] = []
        fallbacks: List[Dict[str, Any]] = []

        action = intent.action
        params = intent.parameters
        coords = intent.coordinates

        if action == "click":
            step = {
                "tool": "orb_click",
                "args": {
                    "x": coords.get("x", params.get("x", 0)),
                    "y": coords.get("y", params.get("y", 0)),
                    "button": params.get("button", "left"),
                }
            }
            steps.append(step)
            # Fallback: screenshot to verify
            fallbacks.append({
                "tool": "orb_screenshot",
                "args": {"width": 1024}
            })

        elif action == "type":
            text = params.get("text", intent.raw_input)
            steps.append({
                "tool": "orb_type",
                "args": {
                    "text": text,
                    "press_enter": params.get("press_enter", False),
                }
            })
            fallbacks.append({
                "tool": "orb_clipboard_write",
                "args": {"text": text}
            })

        elif action == "scroll":
            steps.append({
                "tool": "orb_scroll",
                "args": {
                    "x": coords.get("x", params.get("x", 500)),
                    "y": coords.get("y", params.get("y", 400)),
                    "direction": params.get("direction", "down"),
                    "amount": params.get("amount", 5),
                }
            })
            fallbacks.append({
                "tool": "orb_screenshot",
                "args": {"width": 1024}
            })

        elif action == "move_mouse":
            steps.append({
                "tool": "orb_move_mouse",
                "args": {
                    "x": coords.get("x", params.get("x", 0)),
                    "y": coords.get("y", params.get("y", 0)),
                }
            })

        elif action == "screenshot":
            steps.append({
                "tool": "orb_screenshot",
                "args": {"width": params.get("width", 1024)}
            })

        elif action == "open_app":
            bundle = params.get("bundle_id", intent.target)
            steps.append({
                "tool": "orb_open_app",
                "args": {"bundle_id": bundle}
            })
            fallbacks.append({
                "tool": "orb_screenshot",
                "args": {"width": 1024}
            })

        elif action == "navigate":
            # Ensure browser open first
            steps.append({
                "tool": "orb_browser_open",
                "args": {"browser": "chrome"}
            })
            steps.append({
                "tool": "orb_browser_navigate",
                "args": {"url": params.get("url", intent.target)}
            })
            fallbacks.append({
                "tool": "orb_screenshot",
                "args": {"width": 1024}
            })

        elif action == "wait":
            steps.append({
                "tool": "orb_wait",
                "args": {"seconds": params.get("seconds", 1.0)}
            })

        elif action == "snapshot":
            steps.append({
                "tool": "orb_snapshot",
                "args": {"use_vision": True}
            })

        elif action == "clipboard_read":
            steps.append({
                "tool": "orb_clipboard_read",
                "args": {}
            })

        elif action == "clipboard_write":
            steps.append({
                "tool": "orb_clipboard_write",
                "args": {"text": params.get("text", "")}
            })

        elif action == "list_windows":
            steps.append({
                "tool": "orb_list_windows",
                "args": {}
            })

        else:
            # Unknown — fallback to screenshot for diagnosis
            steps.append({
                "tool": "orb_screenshot",
                "args": {"width": 1024}
            })

        return ExecutionPlan(
            steps=steps,
            fallback_steps=fallbacks,
            intent_summary=f"{action} → {intent.target or 'no target'}",
            estimated_confidence=intent.confidence,
        )


# ──────────────────────────────────────────────
# Reconciler
# ──────────────────────────────────────────────

class TPCReconciler:
    """
    Resolution Trinity — axis_3 of TPC.
    Reconciles execution results against the original plan.
    Routes through R-Substrate for final confidence calibration.
    """

    def __init__(self):
        self._substrate = get_r_substrate()

    def reconcile(
        self,
        plan: ExecutionPlan,
        executed: List[Dict[str, Any]],
        verdicts: List[Any],
    ) -> Dict[str, Any]:
        total        = len(plan.steps)
        executed_cnt = len(executed)
        pass_cnt     = sum(1 for v in verdicts if getattr(v, "verdict", "") == "PASS")
        fallback_cnt = max(0, executed_cnt - total)

        completion  = executed_cnt / max(total, 1)
        pass_rate   = pass_cnt / max(executed_cnt, 1)
        usable      = pass_rate >= 0.5 and completion >= 0.5

        # Build signal for substrate re-routing
        signal = {
            "action":         "reconcile",
            "plan_steps":     total,
            "executed_steps": executed_cnt,
            "pass_rate":      pass_rate,
            "dependencies_met": usable,
            "state_valid":    usable,
        }
        verdict = self._substrate.route(signal)

        capped_conf  = min(verdict.confidence, pass_rate)
        recommendation = (
            "PROCEED"  if capped_conf >= 0.65 else
            "VERIFY"   if capped_conf >= 0.40 else
            "RETRY"
        )

        return {
            "usable":      usable,
            "pass_rate":   round(pass_rate, 4),
            "completion":  round(completion, 4),
            "fallbacks_used": fallback_cnt > 0,
            "warnings":    verdict.warnings,
            "axis_2_coherence": {
                "fallbacks_used": fallback_cnt > 0,
                "execution_ratio": round(completion, 4),
            },
            "axis_3_calibration": {
                "capped_confidence": round(capped_conf, 4),
                "recommendation":    recommendation,
                "substrate_state":   verdict.state.value,
            }
        }


# ──────────────────────────────────────────────
# TPC Core — unified entry point
# ──────────────────────────────────────────────

class TPCCore:
    """
    Triple Predicate Cubed engine.
    Wires parser → substrate → plan generator → reconciler.
    All requests go through R-Substrate before execution.
    """

    def __init__(self):
        self._parser     = TPCIntentParser()
        self._planner    = TPCPlanGenerator()
        self._reconciler = TPCReconciler()
        self._substrate  = get_r_substrate()

    def parse_intent(self, raw_command: str) -> ParsedIntent:
        """
        Parse raw command through TPC Input Trinity + R-Substrate.
        Returns a ParsedIntent with ECM-calibrated confidence.
        """
        action, target, coords, params = self._parser.parse(raw_command)

        # Build substrate signal
        signal = {
            "raw_input":   raw_command,
            "action":      action,
            "target":      target,
            "coordinates": coords,
            "args":        params,
            "plan_steps":  1,
            "dependencies_met": True,
            "state_valid": True,
            "context":     raw_command,
        }

        verdict = self._substrate.route(signal)

        requires_clarification = (
            not action or
            verdict.state == ConvergenceState.BLOCKED or
            verdict.confidence < 0.30
        )

        return ParsedIntent(
            raw_input=raw_command,
            action=action,
            target=target,
            coordinates=coords,
            parameters=params,
            confidence=verdict.confidence,
            requires_clarification=requires_clarification,
            substrate_state=verdict.state.value,
            signal_hash=verdict.signal_hash,
            warnings=verdict.warnings,
        )

    def generate_plan(self, intent: ParsedIntent) -> ExecutionPlan:
        """Generate deterministic execution plan from parsed intent."""
        return self._planner.generate(intent)

    def reconcile_execution_result(
        self,
        plan: ExecutionPlan,
        executed: List[Dict[str, Any]],
        verdicts: List[Any],
    ) -> Dict[str, Any]:
        """Reconcile execution results. Returns structured reconciliation dict."""
        return self._reconciler.reconcile(plan, executed, verdicts)

    def get_clarification_request(self, intent: ParsedIntent) -> str:
        """Generate human-readable clarification prompt for ambiguous commands."""
        base = (
            f"TPC could not resolve: '{intent.raw_input}'\n"
            f"Substrate state: {intent.substrate_state} | "
            f"Confidence: {intent.confidence:.2f}\n\n"
        )

        if not intent.action:
            return base + (
                "No recognisable action found. Try:\n"
                "  • 'click at 500 300'\n"
                "  • 'type \"hello world\"'\n"
                "  • 'scroll down 5'\n"
                "  • 'navigate to example.com'\n"
                "  • 'screenshot'\n"
                "  • 'open chrome'"
            )

        if not intent.coordinates and intent.action in ("click", "scroll", "move_mouse"):
            return base + (
                f"Action '{intent.action}' requires screen coordinates.\n"
                f"Provide: '{intent.action} at X Y'  (e.g., '{intent.action} at 500 300')"
            )

        return base + "Please rephrase or provide more specific details."

    def substrate_status(self) -> Dict[str, Any]:
        """Return current substrate diagnostics."""
        return {
            "round_trip_ms": self._substrate.last_round_trip_ms(),
            "recent_verdicts": self._substrate.verdict_log()[-3:],
        }


# ── Singleton accessor ────────────────────────────────────────────────────────

_tpc_singleton: Optional[TPCCore] = None

def get_tpc_core() -> TPCCore:
    global _tpc_singleton
    if _tpc_singleton is None:
        _tpc_singleton = TPCCore()
    return _tpc_singleton
