
"""
orb_state_machine.py — CALI Orb Four-Layer State Authority

Architectural principle: CALI owns the truth. All modules operate on it.
Four layers:
  desired:    What DockStation/Bridge asks for (user intent)
  runtime:    What subprocesses report as actually alive (ground truth)
  effective:  What CALI authorizes (intersection of desired + runtime + policy)
  activity:   What's actively happening right now (execution state)

Every state report carries source + timestamp + error context.
Every command carries full lifecycle: ACCEPTED → EXECUTING → COMPLETED/FAILED/TIMEOUT
Motion is tied to named target + completion event, not just enabled flag.

Author: CALI v3.5+ State Machine Refactor
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Callable
from enum import Enum, auto
from pathlib import Path


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------

class CommandPhase(Enum):
    """Lifecycle phases for every command crossing the bridge."""
    ACCEPTED   = auto()   # Bridge received, CALI acknowledged
    EXECUTING  = auto()   # CALI began work
    COMPLETED  = auto()   # Success
    FAILED     = auto()   # Error during execution
    TIMEOUT    = auto()   # Exceeded deadline
    CANCELLED  = auto()   # Explicitly aborted


class MotionTarget(Enum):
    """Named movement destinations for the ORB."""
    CURSOR          = "cursor"
    DOCK            = "dock"
    SCREEN_POSITION = "screen_position"
    PAGE_TARGET     = "page_target"
    IDLE            = "idle"


# ------------------------------------------------------------------
# Data Classes
# ------------------------------------------------------------------

@dataclass
class StateReport:
    """A single state variable with full provenance."""
    value: Any
    source: str           # e.g. "MicCapture", "TTSClient", "bridge", "policy"
    checked_at: float       # time.time()
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["checked_at_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.checked_at))
        return d


@dataclass
class CommandLifecycle:
    """Full audit trail for one bridge command."""
    request_id: str
    command_type: str
    payload: dict
    phase: CommandPhase = CommandPhase.ACCEPTED
    accepted_at: float = field(default_factory=time.time)
    executing_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    source: str = "bridge"  # who initiated

    def transition(self, phase: CommandPhase, result=None, error=None):
        self.phase = phase
        if phase == CommandPhase.EXECUTING and self.executing_at is None:
            self.executing_at = time.time()
        if phase in (CommandPhase.COMPLETED, CommandPhase.FAILED, CommandPhase.TIMEOUT, CommandPhase.CANCELLED):
            self.completed_at = time.time()
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "command_type": self.command_type,
            "phase": self.phase.name,
            "source": self.source,
            "accepted_at": self.accepted_at,
            "executing_at": self.executing_at,
            "completed_at": self.completed_at,
            "duration_ms": round((self.completed_at or time.time()) - self.accepted_at, 3) * 1000 if self.accepted_at else None,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class MotionState:
    """Motion is tied to named target + completion event."""
    target: MotionTarget = MotionTarget.IDLE
    target_position: Optional[tuple] = None  # (x, y) for SCREEN_POSITION
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None  # "success", "blocked", "timeout", etc.
    enabled: bool = False

    def to_dict(self) -> dict:
        return {
            "target": self.target.value,
            "target_position": self.target_position,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "enabled": self.enabled,
        }


# ------------------------------------------------------------------
# Core State Machine
# ------------------------------------------------------------------

class CALIStateMachine:
    """
    Four-layer state authority for CALI Orb.

    DOMAINS: listening, voice, motion, presence, cognition, command, system

    Usage:
        sm = CALIStateMachine()
        sm.set_desired_state("listening", {"enabled": True}, source="bridge")
        sm.update_runtime_state("listening", {"mic_available": False}, source="MicCapture")
        effective = sm.derive_effective_state("listening")
        # effective.can_listen = False, block_reason = "mic_unavailable"
    """

    DOMAINS = {
        "listening", "voice", "motion", "presence",
        "cognition", "command", "system"
    }

    def __init__(self, checkout_path: Optional[Path] = None):
        self._lock = threading.RLock()
        self.checkout_path = checkout_path or Path(__file__).parent.resolve()

        # Four layers
        self._desired:  Dict[str, Dict[str, StateReport]] = {d: {} for d in self.DOMAINS}
        self._runtime:  Dict[str, Dict[str, StateReport]] = {d: {} for d in self.DOMAINS}
        self._effective: Dict[str, Dict[str, Any]] = {d: {} for d in self.DOMAINS}
        self._activity: Dict[str, Dict[str, Any]] = {d: {} for d in self.DOMAINS}

        # Command lifecycle ledger (append-only)
        self._commands: Dict[str, CommandLifecycle] = {}
        self._command_history: List[str] = []  # ordered request_ids

        # Motion state (specialized)
        self._motion = MotionState()

        # Callbacks for state change notifications
        self._listeners: List[Callable[[str, dict], None]] = []

        # Initialize defaults
        self._init_defaults()

    def _init_defaults(self):
        """Seed default desired states."""
        with self._lock:
            self._desired["system"]["orb_alive"] = StateReport(
                value=True, source="init", checked_at=time.time()
            )
            self._desired["listening"]["enabled"] = StateReport(
                value=False, source="init", checked_at=time.time()
            )
            self._desired["voice"]["enabled"] = StateReport(
                value=True, source="init", checked_at=time.time()
            )
            self._desired["motion"]["enabled"] = StateReport(
                value=True, source="init", checked_at=time.time()
            )
            self._desired["cognition"]["enabled"] = StateReport(
                value=True, source="init", checked_at=time.time()
            )
            # Derive initial effective states
            for domain in self.DOMAINS:
                self._derive_effective_locked(domain)

    # ------------------------------------------------------------------
    # Checkout validation
    # ------------------------------------------------------------------

    def validate_checkout(self, file_path: Path) -> bool:
        """
        Active checkout problem: a file is only relevant if it belongs
        to the exact checkout launched by the current launch_desktop_orb.ps1.
        """
        try:
            return file_path.resolve().is_relative_to(self.checkout_path)
        except (ValueError, OSError):
            return False

    def get_checkout_path(self) -> str:
        return str(self.checkout_path)

    # ------------------------------------------------------------------
    # Desired State (what user/bridge wants)
    # ------------------------------------------------------------------

    def set_desired_state(self, domain: str, state_delta: dict, source: str = "bridge") -> dict:
        """
        Set desired state for a domain. Returns the delta applied.

        Example:
            sm.set_desired_state("listening", {"enabled": True}, source="DockStation")
        """
        if domain not in self.DOMAINS:
            raise ValueError(f"Unknown domain: {domain}. Valid: {self.DOMAINS}")

        now = time.time()
        applied = {}
        with self._lock:
            for key, value in state_delta.items():
                report = StateReport(value=value, source=source, checked_at=now)
                self._desired[domain][key] = report
                applied[key] = report.to_dict()

            # Re-derive effective state whenever desired changes
            self._derive_effective_locked(domain)

        self._notify(domain, {"layer": "desired", "delta": applied})
        return applied

    def get_desired_state(self, domain: str) -> dict:
        """Pure read of desired layer."""
        with self._lock:
            return {k: v.to_dict() for k, v in self._desired.get(domain, {}).items()}

    # ------------------------------------------------------------------
    # Runtime State (what subprocesses report as ground truth)
    # ------------------------------------------------------------------

    def update_runtime_state(self, domain: str, report: dict, source: str = "runtime") -> dict:
        """
        Update runtime state from a subsystem probe.

        Example:
            sm.update_runtime_state("listening", {
                "mic_available": False,
                "mic_error": "timeout waiting for CP3 listener ready"
            }, source="MicCapture")
        """
        if domain not in self.DOMAINS:
            raise ValueError(f"Unknown domain: {domain}")

        now = time.time()
        applied = {}
        with self._lock:
            for key, value in report.items():
                # Special handling for error keys
                error = None
                if key.endswith("_error"):
                    error = value
                    # Store the error on the base key's report
                    base_key = key[:-6]
                    if base_key in self._runtime[domain]:
                        self._runtime[domain][base_key].error = value
                    continue

                state_report = StateReport(value=value, source=source, checked_at=now, error=error)
                self._runtime[domain][key] = state_report
                applied[key] = state_report.to_dict()

            # Re-derive effective state whenever runtime changes
            self._derive_effective_locked(domain)

        self._notify(domain, {"layer": "runtime", "delta": applied})
        return applied

    def get_runtime_state(self, domain: str) -> dict:
        """Pure read of runtime layer."""
        with self._lock:
            return {k: v.to_dict() for k, v in self._runtime.get(domain, {}).items()}

    # ------------------------------------------------------------------
    # Effective State (what CALI authorizes — intersection + policy)
    # ------------------------------------------------------------------

    def _derive_effective_locked(self, domain: str):
        """
        Derive effective state from desired + runtime + policy.
        Called inside lock.
        """
        desired = self._desired.get(domain, {})
        runtime = self._runtime.get(domain, {})
        effective = {}

        if domain == "listening":
            want_listen = desired.get("enabled", StateReport(False, "default", 0)).value
            mic_ok = runtime.get("mic_available", StateReport(False, "default", 0)).value
            cp3_ok = runtime.get("cp3_ready", StateReport(False, "default", 0)).value

            effective["can_listen"] = want_listen and mic_ok and cp3_ok
            effective["want_listen"] = want_listen
            effective["mic_available"] = mic_ok
            effective["cp3_ready"] = cp3_ok

            if not mic_ok:
                mic_report = runtime.get("mic_available", StateReport(False, "unknown", 0))
                effective["block_reason"] = mic_report.error or "mic_unavailable"
                effective["block_source"] = mic_report.source
                effective["block_checked_at"] = mic_report.checked_at
            elif not cp3_ok:
                cp3_report = runtime.get("cp3_ready", StateReport(False, "unknown", 0))
                effective["block_reason"] = cp3_report.error or "cp3_not_ready"
                effective["block_source"] = cp3_report.source
                effective["block_checked_at"] = cp3_report.checked_at
            else:
                effective["block_reason"] = None
                effective["block_source"] = None
                effective["block_checked_at"] = None

        elif domain == "voice":
            want_voice = desired.get("enabled", StateReport(True, "default", 0)).value
            tts_ok = runtime.get("tts_ready", StateReport(False, "default", 0)).value

            effective["can_speak"] = want_voice and tts_ok
            effective["want_voice"] = want_voice
            effective["tts_ready"] = tts_ok

            if not tts_ok:
                tts_report = runtime.get("tts_ready", StateReport(False, "unknown", 0))
                effective["block_reason"] = tts_report.error or "tts_unavailable"
                effective["block_source"] = tts_report.source
            else:
                effective["block_reason"] = None
                effective["block_source"] = None

        elif domain == "motion":
            want_motion = desired.get("enabled", StateReport(True, "default", 0)).value
            effective["can_move"] = want_motion
            effective["want_motion"] = want_motion
            effective["current_target"] = self._motion.target.value
            effective["motion_result"] = self._motion.result

        elif domain == "cognition":
            want_cog = desired.get("enabled", StateReport(True, "default", 0)).value
            llm_ok = runtime.get("llm_ready", StateReport(False, "default", 0)).value

            effective["can_cognate"] = want_cog and llm_ok
            effective["want_cognition"] = want_cog
            effective["llm_ready"] = llm_ok

            if not llm_ok:
                llm_report = runtime.get("llm_ready", StateReport(False, "unknown", 0))
                effective["block_reason"] = llm_report.error or "llm_unavailable"
                effective["block_source"] = llm_report.source
            else:
                effective["block_reason"] = None

        elif domain == "system":
            effective["orb_alive"] = desired.get("orb_alive", StateReport(True, "default", 0)).value
            effective["checkout_path"] = str(self.checkout_path)

        elif domain == "command":
            # Command domain effective state is derived from lifecycle ledger
            active_commands = [
                req_id for req_id in self._command_history[-10:]
                if self._commands[req_id].phase in (CommandPhase.ACCEPTED, CommandPhase.EXECUTING)
            ]
            effective["active_commands"] = len(active_commands)
            effective["last_command"] = self._command_history[-1] if self._command_history else None

        elif domain == "presence":
            want_presence = desired.get("enabled", StateReport(True, "default", 0)).value
            effective["can_present"] = want_presence
            effective["want_presence"] = want_presence

        self._effective[domain] = effective

    def derive_effective_state(self, domain: str) -> dict:
        """Public trigger to re-derive effective state. Pure read of result."""
        with self._lock:
            self._derive_effective_locked(domain)
            return dict(self._effective.get(domain, {}))

    def get_effective_state(self, domain: str) -> dict:
        """Pure read of effective layer."""
        with self._lock:
            return dict(self._effective.get(domain, {}))

    # ------------------------------------------------------------------
    # Activity State (what's actively happening right now)
    # ------------------------------------------------------------------

    def set_activity_state(self, domain: str, activity: dict, source: str = "activity") -> dict:
        """
        Set what's actively happening right now.

        Example:
            sm.set_activity_state("listening", {
                "state": "listening_active",
                "trigger": "whistle_detected",
                "started_at": time.time()
            })
        """
        if domain not in self.DOMAINS:
            raise ValueError(f"Unknown domain: {domain}")

        now = time.time()
        with self._lock:
            activity["source"] = source
            activity["set_at"] = now
            self._activity[domain] = activity

        self._notify(domain, {"layer": "activity", "state": activity})
        return activity

    def get_activity_state(self, domain: str) -> dict:
        """Pure read of activity layer."""
        with self._lock:
            activity = self._activity.get(domain, {})
            return dict(activity)

    # ------------------------------------------------------------------
    # Motion State (specialized — named target + completion event)
    # ------------------------------------------------------------------

    def set_motion_target(self, target: MotionTarget, position: Optional[tuple] = None) -> dict:
        """
        Set motion target with completion tracking.

        Example:
            sm.set_motion_target(MotionTarget.CURSOR)
            sm.set_motion_target(MotionTarget.SCREEN_POSITION, (100, 200))
        """
        with self._lock:
            self._motion.target = target
            self._motion.target_position = position
            self._motion.started_at = time.time()
            self._motion.completed_at = None
            self._motion.result = None
            self._motion.enabled = True

            # Update desired state too
            self._desired["motion"]["target"] = StateReport(
                value=target.value, source="motion_controller", checked_at=time.time()
            )
            self._derive_effective_locked("motion")

        self._notify("motion", {"layer": "motion", "target": target.value, "position": position})
        return self._motion.to_dict()

    def complete_motion(self, result: str) -> dict:
        """Mark current motion as completed."""
        with self._lock:
            self._motion.completed_at = time.time()
            self._motion.result = result
            self._motion.enabled = False

        self._notify("motion", {"layer": "motion", "completed": True, "result": result})
        return self._motion.to_dict()

    def get_motion_state(self) -> dict:
        """Pure read of motion state."""
        with self._lock:
            return self._motion.to_dict()

    # ------------------------------------------------------------------
    # Command Lifecycle (ACCEPTED → EXECUTING → COMPLETED/FAILED/TIMEOUT)
    # ------------------------------------------------------------------

    def start_command(self, request_id: str, command_type: str, payload: dict, source: str = "bridge") -> CommandLifecycle:
        """
        Begin tracking a new command.

        Returns the lifecycle object. Callers must hold onto request_id.
        """
        lifecycle = CommandLifecycle(
            request_id=request_id,
            command_type=command_type,
            payload=payload,
            source=source
        )
        with self._lock:
            self._commands[request_id] = lifecycle
            self._command_history.append(request_id)
            # Trim history to last 100
            if len(self._command_history) > 100:
                old = self._command_history.pop(0)
                self._commands.pop(old, None)

        self._notify("command", {"layer": "command", "event": "started", "request_id": request_id})
        return lifecycle

    def transition_command(self, request_id: str, phase: CommandPhase, result=None, error=None) -> Optional[CommandLifecycle]:
        """Transition a command to a new phase."""
        with self._lock:
            lifecycle = self._commands.get(request_id)
            if lifecycle:
                lifecycle.transition(phase, result=result, error=error)
                # Re-derive command effective state
                self._derive_effective_locked("command")

        if lifecycle:
            self._notify("command", {
                "layer": "command",
                "event": "transition",
                "request_id": request_id,
                "phase": phase.name
            })
        return lifecycle

    def get_command_lifecycle(self, request_id: str) -> Optional[dict]:
        """Pure read of one command's lifecycle."""
        with self._lock:
            lifecycle = self._commands.get(request_id)
            return lifecycle.to_dict() if lifecycle else None

    def get_recent_commands(self, limit: int = 10) -> List[dict]:
        """Pure read of recent command history."""
        with self._lock:
            recent = self._command_history[-limit:]
            return [self._commands[rid].to_dict() for rid in recent if rid in self._commands]

    def get_active_commands(self) -> List[dict]:
        """Pure read of currently active commands."""
        with self._lock:
            active = [
                rid for rid in self._command_history
                if self._commands[rid].phase in (CommandPhase.ACCEPTED, CommandPhase.EXECUTING)
            ]
            return [self._commands[rid].to_dict() for rid in active]

    # ------------------------------------------------------------------
    # Full State — Pure Read, No Mutation
    # ------------------------------------------------------------------

    def get_full_state(self) -> dict:
        """
        Pure read of all four layers across all domains.
        No mutation. No probing. Just returns current truth.
        """
        with self._lock:
            return {
                "checkout_path": str(self.checkout_path),
                "timestamp": time.time(),
                "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "desired": {d: {k: v.to_dict() for k, v in self._desired[d].items()} for d in self.DOMAINS},
                "runtime": {d: {k: v.to_dict() for k, v in self._runtime[d].items()} for d in self.DOMAINS},
                "effective": {d: dict(self._effective[d]) for d in self.DOMAINS},
                "activity": {d: dict(self._activity[d]) for d in self.DOMAINS},
                "motion": self._motion.to_dict(),
                "commands": {
                    "active_count": len([r for r in self._command_history[-10:] 
                                         if self._commands[r].phase in (CommandPhase.ACCEPTED, CommandPhase.EXECUTING)]),
                    "recent": [self._commands[rid].to_dict() for rid in self._command_history[-5:] if rid in self._commands]
                }
            }

    def get_status(self) -> dict:
        """
        Backward-compatible status method.
        Returns the effective state in the shape old code expects.
        """
        with self._lock:
            return {
                "listening_mode": {
                    "enabled": self._effective.get("listening", {}).get("can_listen", False),
                    "want_listen": self._effective.get("listening", {}).get("want_listen", False),
                    "mic_available": self._effective.get("listening", {}).get("mic_available", False),
                    "cp3_ready": self._effective.get("listening", {}).get("cp3_ready", False),
                    "block_reason": self._effective.get("listening", {}).get("block_reason"),
                    "block_source": self._effective.get("listening", {}).get("block_source"),
                },
                "voice_status": {
                    "enabled": self._effective.get("voice", {}).get("can_speak", False),
                    "tts_ready": self._effective.get("voice", {}).get("tts_ready", False),
                },
                "motion_status": self._motion.to_dict(),
                "cognition_status": {
                    "enabled": self._effective.get("cognition", {}).get("can_cognate", False),
                    "llm_ready": self._effective.get("cognition", {}).get("llm_ready", False),
                },
                "system_status": {
                    "orb_alive": self._effective.get("system", {}).get("orb_alive", False),
                    "checkout_path": str(self.checkout_path),
                },
                "command_status": {
                    "active_commands": self._effective.get("command", {}).get("active_commands", 0),
                    "last_command": self._effective.get("command", {}).get("last_command"),
                }
            }

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[str, dict], None]):
        """Register a callback for state change notifications."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, dict], None]):
        """Remove a callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, domain: str, event: dict):
        """Notify all listeners of a state change."""
        for cb in self._listeners:
            try:
                cb(domain, event)
            except Exception:
                pass  # Never let a listener break the state machine

    # ------------------------------------------------------------------
    # Debug / Diagnostics
    # ------------------------------------------------------------------

    def diagnose_listening(self) -> dict:
        """
        Deep diagnostic for the listening pipeline.
        Shows exactly where the break is: desired → runtime → effective → activity.
        """
        with self._lock:
            return {
                "desired": self.get_desired_state("listening"),
                "runtime": self.get_runtime_state("listening"),
                "effective": self.get_effective_state("listening"),
                "activity": self.get_activity_state("listening"),
                "diagnosis": self._diagnose_domain_locked("listening")
            }

    def _diagnose_domain_locked(self, domain: str) -> str:
        """Inside lock. Returns human-readable diagnosis."""
        eff = self._effective.get(domain, {})
        if eff.get("can_listen"):
            return f"{domain}: FULLY OPERATIONAL"

        want = self._desired.get(domain, {}).get("enabled", StateReport(False, "unknown", 0)).value
        if not want:
            return f"{domain}: DISABLED BY USER (desired.enabled = False)"

        reason = eff.get("block_reason", "unknown")
        source = eff.get("block_source", "unknown")
        return f"{domain}: BLOCKED — {reason} (reported by {source})"

    def diagnose_command(self, request_id: str) -> Optional[dict]:
        """Full diagnostic for one command's lifecycle."""
        lifecycle = self.get_command_lifecycle(request_id)
        if not lifecycle:
            return None

        # Find the gap
        phase = lifecycle["phase"]
        if phase == "ACCEPTED":
            gap = "Command was accepted but never began executing"
        elif phase == "EXECUTING":
            gap = "Command is executing but never completed"
        elif phase == "FAILED":
            gap = f"Command failed: {lifecycle.get('error')}"
        elif phase == "TIMEOUT":
            gap = f"Command timed out after {lifecycle.get('duration_ms')}ms"
        else:
            gap = "Command completed normally"

        return {
            "lifecycle": lifecycle,
            "gap_analysis": gap,
            "recommendation": self._recommend_for_phase(phase)
        }

    def _recommend_for_phase(self, phase: str) -> str:
        recommendations = {
            "ACCEPTED": "Check if the command handler was invoked. Look for exceptions in the handler thread.",
            "EXECUTING": "Check if the command is blocked on I/O, waiting for a resource, or deadlocked.",
            "FAILED": "Review the error message. Check subsystem health (mic, TTS, LLM).",
            "TIMEOUT": "Increase timeout or check if the operation is hanging on an external resource.",
            "COMPLETED": "No action needed.",
            "CANCELLED": "Command was explicitly cancelled. Check cancellation logic."
        }
        return recommendations.get(phase, "Unknown phase — review logs.")
