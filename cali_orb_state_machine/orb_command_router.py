
"""
orb_command_router.py — Orb Command Router with Full Lifecycle Tracking

Replaces the inline stdin/stdout message loop from floating_assistant_orb.py.
Every command crossing the bridge gets:
  request_id → ACCEPTED → EXECUTING → COMPLETED / FAILED / TIMEOUT

Wire order (from floating_assistant_orb_main.py):
  1. router = OrbCommandRouter(orb)
  2. router.emit_ready()   → sends Electron bridge handshake
  3. router.run()          → blocks on stdin until "shutdown" or EOF

Author: CALI v3.5+ State Machine Refactor
"""

from __future__ import annotations

import sys
import json
import time
import threading
import traceback
import uuid
from typing import Optional, Dict, Any, Callable

from orb_state_machine import CALIStateMachine, CommandPhase


class OrbCommandRouter:
    """
    Routes commands from the Electron bridge (stdin/stdout JSONL)
    through the state machine with full lifecycle tracking.

    Command flow:
      Bridge sends: {"type": "set_listening", "enabled": true, "request_id": "..."}
      Router: ACCEPTED → route to handler → EXECUTING
      Handler: does the work → COMPLETED or FAILED
      Router: emits result back to bridge

    Timeout debugging:
      "listening requested → accepted → listener init started → 
       mic unavailable → FAILED (mic_unavailable)"
    """

    # Command handlers map: command_type → handler method
    HANDLERS: Dict[str, str] = {
        "set_listening": "_handle_set_listening",
        "listen_once": "_handle_listen_once",
        "get_status": "_handle_get_status",
        "get_full_status": "_handle_get_full_status",
        "set_voice": "_handle_set_voice",
        "set_motion": "_handle_set_motion",
        "set_cognition": "_handle_set_cognition",
        "orb_query": "_handle_orb_query",
        "orb_speak": "_handle_orb_speak",
        "shutdown": "_handle_shutdown",
        "diagnose": "_handle_diagnose",
    }

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb
        self.state_machine: CALIStateMachine = getattr(orb, "state_machine", None)
        if self.state_machine is None:
            raise RuntimeError("OrbCommandRouter requires orb.state_machine to be set. "
                               "Ensure OrbLifecycle initialized before CommandRouter.")

        self._running = False
        self._default_timeout = 30.0  # seconds for command execution

    # ------------------------------------------------------------------
    # Bridge Handshake
    # ------------------------------------------------------------------

    def emit_ready(self):
        """
        Send the Electron bridge handshake message.
        Unblocks the renderer waiting for Python to be ready.
        """
        ready_msg = {
            "type": "orb_ready",
            "timestamp": time.time(),
            "version": "3.5-statemachine",
            "checkout_path": self.state_machine.get_checkout_path(),
        }
        self._emit(ready_msg)
        print("[OrbCommandRouter] Bridge handshake emitted.", flush=True)

    def _emit(self, msg: dict):
        """Emit a JSON message to the bridge via stdout."""
        try:
            print(json.dumps(msg), flush=True)
        except Exception as e:
            print(f"[OrbCommandRouter] Emit error: {e}", file=sys.stderr, flush=True)

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------

    def run(self):
        """
        Block on stdin reading JSONL commands until shutdown or EOF.
        Replaces the inline loop in floating_assistant_orb.py.
        """
        print("[OrbCommandRouter] Command router running. Waiting for commands...", flush=True)
        self._running = True

        while self._running:
            try:
                line = sys.stdin.readline()
                if not line:
                    # EOF — stdin closed
                    print("[OrbCommandRouter] EOF on stdin. Shutting down.", flush=True)
                    self._running = False
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    command = json.loads(line)
                except json.JSONDecodeError as e:
                    self._emit({
                        "type": "error",
                        "error": f"Invalid JSON: {e}",
                        "raw": line[:200]
                    })
                    continue

                # Route the command with full lifecycle tracking
                self._route_command(command)

            except KeyboardInterrupt:
                print("[OrbCommandRouter] Keyboard interrupt. Shutting down.", flush=True)
                self._running = False
                break
            except Exception as e:
                print(f"[OrbCommandRouter] Loop error: {e}", file=sys.stderr, flush=True)
                traceback.print_exc()

        print("[OrbCommandRouter] Command router stopped.", flush=True)

    def stop(self):
        """Signal the run loop to stop."""
        self._running = False

    # ------------------------------------------------------------------
    # Command Routing with Lifecycle
    # ------------------------------------------------------------------

    def _route_command(self, command: dict):
        """
        Route a single command through the full lifecycle.

        command: {"type": "set_listening", "enabled": true, "request_id": "..."}
        """
        cmd_type = command.get("type", "unknown")
        request_id = command.get("request_id", str(uuid.uuid4())[:8])

        # 1. ACCEPTED — register in state machine
        lifecycle = self.state_machine.start_command(
            request_id=request_id,
            command_type=cmd_type,
            payload=command,
            source="bridge"
        )

        # Emit ACCEPTED acknowledgment
        self._emit({
            "type": "command_accepted",
            "request_id": request_id,
            "command_type": cmd_type,
        })

        # Find handler
        handler_name = self.HANDLERS.get(cmd_type)
        if not handler_name:
            # Unknown command — fail fast
            self.state_machine.transition_command(
                request_id, CommandPhase.FAILED,
                error=f"Unknown command type: {cmd_type}"
            )
            self._emit({
                "type": "command_failed",
                "request_id": request_id,
                "command_type": cmd_type,
                "error": f"Unknown command type: {cmd_type}",
            })
            return

        handler = getattr(self, handler_name)

        # 2. EXECUTING — start the handler in a thread with timeout
        self.state_machine.transition_command(request_id, CommandPhase.EXECUTING)

        # Run handler with timeout
        result_container = {"result": None, "error": None, "done": False}

        def _run_handler():
            try:
                result = handler(command, request_id)
                result_container["result"] = result
                result_container["done"] = True
            except Exception as e:
                result_container["error"] = str(e)
                result_container["done"] = True
                traceback.print_exc()

        handler_thread = threading.Thread(target=_run_handler, name=f"cmd-{request_id}")
        handler_thread.start()
        handler_thread.join(timeout=self._default_timeout)

        # 3. COMPLETED / FAILED / TIMEOUT
        if not result_container["done"]:
            # Timeout
            self.state_machine.transition_command(
                request_id, CommandPhase.TIMEOUT,
                error=f"Command timed out after {self._default_timeout}s"
            )
            self._emit({
                "type": "command_timeout",
                "request_id": request_id,
                "command_type": cmd_type,
                "timeout_seconds": self._default_timeout,
            })
        elif result_container["error"]:
            # Failed
            self.state_machine.transition_command(
                request_id, CommandPhase.FAILED,
                error=result_container["error"]
            )
            self._emit({
                "type": "command_failed",
                "request_id": request_id,
                "command_type": cmd_type,
                "error": result_container["error"],
            })
        else:
            # Completed
            self.state_machine.transition_command(
                request_id, CommandPhase.COMPLETED,
                result=result_container["result"]
            )
            self._emit({
                "type": "command_completed",
                "request_id": request_id,
                "command_type": cmd_type,
                "result": result_container["result"],
            })

    # ------------------------------------------------------------------
    # Command Handlers
    # ------------------------------------------------------------------

    def _handle_set_listening(self, command: dict, request_id: str) -> dict:
        """
        Handle set_listening command.

        Flow:
          desired.listening.enabled = true
          → derive effective
          → if effective.can_listen: start listening
          → else: return block_reason
        """
        enabled = command.get("enabled", False)

        # Set desired state
        self.state_machine.set_desired_state(
            "listening", {"enabled": enabled}, source="bridge"
        )

        # Get effective state (derived automatically)
        effective = self.state_machine.get_effective_state("listening")

        can_listen = effective.get("can_listen", False)

        if can_listen:
            # Actually start listening
            if enabled:
                # Call the orb's actual listening start method
                listen_method = getattr(self.orb, "start_listening", None)
                if listen_method:
                    listen_method()

                self.state_machine.set_activity_state("listening", {
                    "state": "listening_active",
                    "trigger": "user_request",
                    "request_id": request_id,
                })
            else:
                # Stop listening
                stop_method = getattr(self.orb, "stop_listening", None)
                if stop_method:
                    stop_method()

                self.state_machine.set_activity_state("listening", {
                    "state": "listening_inactive",
                    "trigger": "user_request",
                    "request_id": request_id,
                })

        return {
            "listening_enabled": enabled,
            "can_listen": can_listen,
            "block_reason": effective.get("block_reason"),
            "block_source": effective.get("block_source"),
            "effective": effective,
        }

    def _handle_listen_once(self, command: dict, request_id: str) -> dict:
        """Handle one-shot listen command."""
        # Set desired state temporarily
        self.state_machine.set_desired_state(
            "listening", {"enabled": True}, source="bridge"
        )

        effective = self.state_machine.get_effective_state("listening")

        if not effective.get("can_listen"):
            return {
                "success": False,
                "block_reason": effective.get("block_reason"),
                "block_source": effective.get("block_source"),
            }

        # Call orb's listen_once
        listen_once = getattr(self.orb, "listen_once", None)
        if listen_once:
            result = listen_once()
            return {"success": True, "result": result}

        return {"success": False, "error": "listen_once not available on orb"}

    def _handle_get_status(self, command: dict, request_id: str) -> dict:
        """
        PURE READ. Return current effective state.
        Never probes, never mutates.
        """
        status = self.state_machine.get_status()
        return {"status": status}

    def _handle_get_full_status(self, command: dict, request_id: str) -> dict:
        """Return complete four-layer state dump."""
        full = self.state_machine.get_full_state()
        return {"full_state": full}

    def _handle_set_voice(self, command: dict, request_id: str) -> dict:
        """Handle set_voice command."""
        enabled = command.get("enabled", True)

        self.state_machine.set_desired_state(
            "voice", {"enabled": enabled}, source="bridge"
        )

        effective = self.state_machine.get_effective_state("voice")

        return {
            "voice_enabled": enabled,
            "can_speak": effective.get("can_speak", False),
            "block_reason": effective.get("block_reason"),
        }

    def _handle_set_motion(self, command: dict, request_id: str) -> dict:
        """
        Handle set_motion command with named target.

        command: {"type": "set_motion", "target": "cursor", "enabled": true}
        """
        enabled = command.get("enabled", True)
        target_str = command.get("target", "idle")
        position = command.get("position")  # (x, y) for screen_position

        from orb_state_machine import MotionTarget

        try:
            target = MotionTarget(target_str)
        except ValueError:
            return {
                "success": False,
                "error": f"Unknown motion target: {target_str}",
                "valid_targets": [t.value for t in MotionTarget],
            }

        self.state_machine.set_desired_state(
            "motion", {"enabled": enabled}, source="bridge"
        )

        if enabled:
            self.state_machine.set_motion_target(target, position)

            # Call orb's motion method
            motion_method = getattr(self.orb, "move_to_target", None)
            if motion_method:
                motion_method(target.value, position)
        else:
            self.state_machine.complete_motion("disabled_by_user")

        effective = self.state_machine.get_effective_state("motion")
        motion = self.state_machine.get_motion_state()

        return {
            "motion_enabled": enabled,
            "target": target.value,
            "position": position,
            "can_move": effective.get("can_move", False),
            "motion_state": motion,
        }

    def _handle_set_cognition(self, command: dict, request_id: str) -> dict:
        """Handle set_cognition command."""
        enabled = command.get("enabled", True)

        self.state_machine.set_desired_state(
            "cognition", {"enabled": enabled}, source="bridge"
        )

        effective = self.state_machine.get_effective_state("cognition")

        return {
            "cognition_enabled": enabled,
            "can_cognate": effective.get("can_cognate", False),
            "block_reason": effective.get("block_reason"),
        }

    def _handle_orb_query(self, command: dict, request_id: str) -> dict:
        """Handle natural language query to the ORB."""
        query = command.get("query", "")

        self.state_machine.set_activity_state("cognition", {
            "state": "processing_query",
            "query": query,
            "request_id": request_id,
        })

        # Call orb's query handler
        query_method = getattr(self.orb, "process_query", None)
        if query_method:
            result = query_method(query)
            return {"success": True, "result": result}

        return {"success": False, "error": "process_query not available on orb"}

    def _handle_orb_speak(self, command: dict, request_id: str) -> dict:
        """Handle TTS speak command."""
        text = command.get("text", "")

        effective = self.state_machine.get_effective_state("voice")
        if not effective.get("can_speak"):
            return {
                "success": False,
                "block_reason": effective.get("block_reason"),
                "block_source": effective.get("block_source"),
            }

        self.state_machine.set_activity_state("voice", {
            "state": "speaking",
            "text": text,
            "request_id": request_id,
        })

        # Call orb's speak method
        speak_method = getattr(self.orb, "speak", None)
        if speak_method:
            speak_method(text)
            return {"success": True, "spoken": text}

        return {"success": False, "error": "speak not available on orb"}

    def _handle_shutdown(self, command: dict, request_id: str) -> dict:
        """Handle graceful shutdown."""
        self.state_machine.set_desired_state(
            "system", {"orb_alive": False}, source="bridge"
        )

        # Signal lifecycle to stop
        lifecycle = getattr(self.orb, "lifecycle", None)
        if lifecycle:
            lifecycle.stop()

        self._running = False
        return {"success": True, "message": "Shutdown initiated"}

    def _handle_diagnose(self, command: dict, request_id: str) -> dict:
        """Handle diagnostic request."""
        domain = command.get("domain", "listening")

        lifecycle = getattr(self.orb, "lifecycle", None)
        if lifecycle:
            return lifecycle.get_diagnostic(domain)

        # Fallback to state machine direct
        if domain == "listening":
            return self.state_machine.diagnose_listening()

        return {
            "desired": self.state_machine.get_desired_state(domain),
            "runtime": self.state_machine.get_runtime_state(domain),
            "effective": self.state_machine.get_effective_state(domain),
            "activity": self.state_machine.get_activity_state(domain),
        }
