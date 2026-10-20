
"""
orb_behavior_runtime.py — Orb Behavior Runtime Delegation

Wraps all behavior methods (cursor, cognition, whistle, verbal)
through the state machine. Ensures every behavior is:
  1. Checked against effective state (can we do this?)
  2. Tracked in activity state (what's happening now?)
  3. Completed with result (what happened?)

Wire order (from floating_assistant_orb_main.py):
  1. orb.behavior_runtime = OrbBehaviorRuntime(orb)
  2. orb.process_cursor_movement = orb.behavior_runtime.process_cursor_movement
  3. orb.cognitively_emerge = orb.behavior_runtime.cognitively_emerge
  4. orb.idle_cognition = orb.behavior_runtime.idle_cognition
  5. orb._detect_whistle_summon = orb.behavior_runtime.detect_whistle_summon
  6. orb._is_cali_summon_request = orb.behavior_runtime.is_cali_summon_request
  7. orb._process_verbal_command = orb.behavior_runtime.process_verbal_command

Author: CALI v3.5+ State Machine Refactor
"""

from __future__ import annotations

import time
import threading
from typing import Optional, Dict, Any, Tuple

from orb_state_machine import CALIStateMachine, MotionTarget


class OrbBehaviorRuntime:
    """
    Delegates all ORB behaviors through the state machine.

    Every behavior method:
      1. Checks effective state (are we allowed?)
      2. Sets activity state (we're doing this now)
      3. Executes the actual behavior
      4. Records completion (success/failure)
    """

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb
        self.state_machine: CALIStateMachine = getattr(orb, "state_machine", None)
        if self.state_machine is None:
            raise RuntimeError("OrbBehaviorRuntime requires orb.state_machine. "
                               "Ensure OrbLifecycle initialized before BehaviorRuntime.")

        # Track current idle cognition thread
        self._idle_thread: Optional[threading.Thread] = None
        self._idle_stop = threading.Event()

    # ------------------------------------------------------------------
    # Cursor Movement
    # ------------------------------------------------------------------

    def process_cursor_movement(self, cursor_x: int, cursor_y: int) -> dict:
        """
        Process cursor position update.

        Motion must be tied to named target and completion event.
        """
        effective = self.state_machine.get_effective_state("motion")

        if not effective.get("can_move", False):
            return {
                "moved": False,
                "reason": effective.get("block_reason", "motion_disabled"),
                "source": effective.get("block_source", "policy"),
            }

        # Set motion target to cursor
        self.state_machine.set_motion_target(MotionTarget.CURSOR)

        # Call actual cursor handler on orb
        cursor_method = getattr(self.orb, "_original_process_cursor", None)
        if cursor_method is None:
            # Try to find the original method stored during _attach_modules
            cursor_method = getattr(self.orb, "process_cursor_movement", None)

        result = None
        if cursor_method and cursor_method != self.process_cursor_movement:
            try:
                result = cursor_method(cursor_x, cursor_y)
                self.state_machine.complete_motion("success")
            except Exception as e:
                self.state_machine.complete_motion(f"error: {e}")
                return {"moved": False, "error": str(e)}
        else:
            # No original method — just record the intent
            self.state_machine.complete_motion("no_handler")

        return {
            "moved": True,
            "cursor": (cursor_x, cursor_y),
            "target": MotionTarget.CURSOR.value,
            "result": result,
        }

    # ------------------------------------------------------------------
    # Cognitive Emergence
    # ------------------------------------------------------------------

    def cognitively_emerge(self, context: Optional[dict] = None) -> dict:
        """
        Trigger cognitive emergence (ORB "wakes up" or becomes aware).

        Checks cognition effective state before executing.
        """
        effective = self.state_machine.get_effective_state("cognition")

        if not effective.get("can_cognate", False):
            return {
                "emerged": False,
                "reason": effective.get("block_reason", "cognition_disabled"),
                "source": effective.get("block_source", "policy"),
            }

        self.state_machine.set_activity_state("cognition", {
            "state": "emerging",
            "trigger": context.get("trigger", "unknown") if context else "unknown",
            "started_at": time.time(),
        })

        # Call original emergence method
        emerge_method = getattr(self.orb, "_original_cognitively_emerge", None)
        if emerge_method is None:
            emerge_method = getattr(self.orb, "cognitively_emerge", None)

        result = None
        if emerge_method and emerge_method != self.cognitively_emerge:
            try:
                result = emerge_method(context)
                self.state_machine.set_activity_state("cognition", {
                    "state": "emerged",
                    "result": "success",
                    "completed_at": time.time(),
                })
            except Exception as e:
                self.state_machine.set_activity_state("cognition", {
                    "state": "emerge_failed",
                    "error": str(e),
                    "completed_at": time.time(),
                })
                return {"emerged": False, "error": str(e)}
        else:
            self.state_machine.set_activity_state("cognition", {
                "state": "emerged",
                "result": "no_handler",
                "completed_at": time.time(),
            })

        return {
            "emerged": True,
            "result": result,
        }

    # ------------------------------------------------------------------
    # Idle Cognition
    # ------------------------------------------------------------------

    def idle_cognition(self) -> dict:
        """
        Run idle background cognition.

        Only runs if cognition is enabled and not already running.
        """
        effective = self.state_machine.get_effective_state("cognition")

        if not effective.get("can_cognate", False):
            return {
                "ran": False,
                "reason": effective.get("block_reason", "cognition_disabled"),
            }

        # Check if already running
        activity = self.state_machine.get_activity_state("cognition")
        if activity.get("state") == "idle_cognating":
            return {"ran": False, "reason": "already_running"}

        self.state_machine.set_activity_state("cognition", {
            "state": "idle_cognating",
            "started_at": time.time(),
        })

        # Call original idle method
        idle_method = getattr(self.orb, "_original_idle_cognition", None)
        if idle_method is None:
            idle_method = getattr(self.orb, "idle_cognition", None)

        result = None
        if idle_method and idle_method != self.idle_cognition:
            try:
                result = idle_method()
                self.state_machine.set_activity_state("cognition", {
                    "state": "idle_complete",
                    "result": "success",
                    "completed_at": time.time(),
                })
            except Exception as e:
                self.state_machine.set_activity_state("cognition", {
                    "state": "idle_failed",
                    "error": str(e),
                    "completed_at": time.time(),
                })
                return {"ran": False, "error": str(e)}
        else:
            self.state_machine.set_activity_state("cognition", {
                "state": "idle_complete",
                "result": "no_handler",
                "completed_at": time.time(),
            })

        return {
            "ran": True,
            "result": result,
        }

    def start_idle_loop(self, interval: float = 30.0):
        """
        Start a background thread that runs idle cognition periodically.
        """
        if self._idle_thread and self._idle_thread.is_alive():
            return {"started": False, "reason": "already_running"}

        self._idle_stop.clear()

        def _loop():
            while not self._idle_stop.is_set():
                self.idle_cognition()
                self._idle_stop.wait(interval)

        self._idle_thread = threading.Thread(target=_loop, daemon=True, name="orb-idle-cognition")
        self._idle_thread.start()

        return {"started": True, "interval": interval}

    def stop_idle_loop(self):
        """Stop the idle cognition background thread."""
        self._idle_stop.set()
        if self._idle_thread and self._idle_thread.is_alive():
            self._idle_thread.join(timeout=2.0)
        return {"stopped": True}

    # ------------------------------------------------------------------
    # Whistle Detection
    # ------------------------------------------------------------------

    def detect_whistle_summon(self, audio_buffer: bytes) -> dict:
        """
        Detect whistle pattern in audio buffer.

        Only runs if listening is effectively enabled.
        """
        effective = self.state_machine.get_effective_state("listening")

        if not effective.get("can_listen", False):
            return {
                "detected": False,
                "reason": effective.get("block_reason", "listening_disabled"),
                "source": effective.get("block_source", "policy"),
            }

        self.state_machine.set_activity_state("listening", {
            "state": "detecting_whistle",
            "started_at": time.time(),
        })

        # Call original whistle detection
        whistle_method = getattr(self.orb, "_original_detect_whistle", None)
        if whistle_method is None:
            whistle_method = getattr(self.orb, "_detect_whistle_summon", None)

        detected = False
        if whistle_method and whistle_method != self.detect_whistle_summon:
            try:
                detected = whistle_method(audio_buffer)
                self.state_machine.set_activity_state("listening", {
                    "state": "whistle_detected" if detected else "whistle_not_detected",
                    "detected": detected,
                    "completed_at": time.time(),
                })
            except Exception as e:
                self.state_machine.set_activity_state("listening", {
                    "state": "whistle_error",
                    "error": str(e),
                    "completed_at": time.time(),
                })
                return {"detected": False, "error": str(e)}
        else:
            self.state_machine.set_activity_state("listening", {
                "state": "whistle_not_detected",
                "detected": False,
                "completed_at": time.time(),
            })

        return {"detected": detected}

    # ------------------------------------------------------------------
    # CALI Summon Detection
    # ------------------------------------------------------------------

    def is_cali_summon_request(self, transcript: str) -> dict:
        """
        Check if transcript contains a CALI summon phrase.

        Returns dict with match info, not just boolean.
        """
        effective = self.state_machine.get_effective_state("listening")

        if not effective.get("can_listen", False):
            return {
                "is_summon": False,
                "reason": effective.get("block_reason", "listening_disabled"),
            }

        # Call original summon detection
        summon_method = getattr(self.orb, "_original_is_cali_summon", None)
        if summon_method is None:
            summon_method = getattr(self.orb, "_is_cali_summon_request", None)

        is_summon = False
        confidence = 0.0
        matched_phrase = None

        if summon_method and summon_method != self.is_cali_summon_request:
            try:
                # Original might return bool or tuple
                result = summon_method(transcript)
                if isinstance(result, tuple):
                    is_summon, confidence, matched_phrase = result
                else:
                    is_summon = bool(result)
                    confidence = 1.0 if is_summon else 0.0
            except Exception as e:
                return {"is_summon": False, "error": str(e)}
        else:
            # Default summon phrases
            summon_phrases = ["hey cali", "okay cali", "cali listen", "wake up cali"]
            lower = transcript.lower()
            for phrase in summon_phrases:
                if phrase in lower:
                    is_summon = True
                    confidence = 0.9
                    matched_phrase = phrase
                    break

        if is_summon:
            self.state_machine.set_activity_state("listening", {
                "state": "summon_detected",
                "phrase": matched_phrase,
                "confidence": confidence,
                "transcript": transcript,
            })

        return {
            "is_summon": is_summon,
            "confidence": confidence,
            "matched_phrase": matched_phrase,
            "transcript": transcript,
        }

    # ------------------------------------------------------------------
    # Verbal Command Processing
    # ------------------------------------------------------------------

    def process_verbal_command(self, transcript: str, context: Optional[dict] = None) -> dict:
        """
        Process a verbal command after summon detection.

        Full pipeline: summon → listen → process → respond.
        """
        effective = self.state_machine.get_effective_state("listening")

        if not effective.get("can_listen", False):
            return {
                "processed": False,
                "reason": effective.get("block_reason", "listening_disabled"),
                "source": effective.get("block_source", "policy"),
            }

        self.state_machine.set_activity_state("command", {
            "state": "processing_verbal",
            "transcript": transcript,
            "started_at": time.time(),
        })

        # Call original verbal command processor
        verbal_method = getattr(self.orb, "_original_process_verbal", None)
        if verbal_method is None:
            verbal_method = getattr(self.orb, "_process_verbal_command", None)

        result = None
        if verbal_method and verbal_method != self.process_verbal_command:
            try:
                result = verbal_method(transcript, context)
                self.state_machine.set_activity_state("command", {
                    "state": "verbal_processed",
                    "result": "success",
                    "completed_at": time.time(),
                })
            except Exception as e:
                self.state_machine.set_activity_state("command", {
                    "state": "verbal_failed",
                    "error": str(e),
                    "completed_at": time.time(),
                })
                return {"processed": False, "error": str(e)}
        else:
            self.state_machine.set_activity_state("command", {
                "state": "verbal_processed",
                "result": "no_handler",
                "completed_at": time.time(),
            })

        return {
            "processed": True,
            "result": result,
            "transcript": transcript,
        }

    # ------------------------------------------------------------------
    # Full Speech Pipeline
    # ------------------------------------------------------------------

    def process_speech_pipeline(self, audio_buffer: bytes) -> dict:
        """
        Full speech pipeline: detect whistle → transcribe → check summon → process command.

        This is the high-level method that speech_manager would call.
        """
        # Step 1: Whistle detection
        whistle = self.detect_whistle_summon(audio_buffer)
        if not whistle.get("detected"):
            return {"handled": False, "stage": "whistle", "whistle_result": whistle}

        # Step 2: Transcribe (call orb's transcribe method)
        transcribe_method = getattr(self.orb, "transcribe_audio", None)
        if not transcribe_method:
            return {"handled": False, "stage": "transcribe", "error": "transcribe_audio not available"}

        transcript = transcribe_method(audio_buffer)
        if not transcript:
            return {"handled": False, "stage": "transcribe", "error": "empty_transcript"}

        # Step 3: Check summon
        summon = self.is_cali_summon_request(transcript)
        if not summon.get("is_summon"):
            return {
                "handled": False,
                "stage": "summon",
                "transcript": transcript,
                "summon_result": summon,
            }

        # Step 4: Process verbal command
        command_result = self.process_verbal_command(transcript)

        return {
            "handled": True,
            "stage": "complete",
            "transcript": transcript,
            "summon": summon,
            "command_result": command_result,
        }
