
"""
orb_lifecycle.py — Orb Process Lifecycle and Health Management

Wraps CALIFloatingOrb's lifecycle methods to route through CALIStateMachine.
Ensures get_status() is a pure read — no mutation, no probing.

Wire order (from floating_assistant_orb_main.py):
  1. orb = CALIFloatingOrb(PROJECT_ROOT)
  2. _attach_modules(orb)  → orb.lifecycle = OrbLifecycle(orb)
  3. orb.start()           → OrbLifecycle.start()
  4. orb.get_status()      → OrbLifecycle.get_status()  [PURE READ]
  5. orb.stop()            → OrbLifecycle.stop()

Author: CALI v3.5+ State Machine Refactor
"""

from __future__ import annotations

import time
import threading
import traceback
from typing import Optional, Dict, Any
from pathlib import Path

from orb_state_machine import CALIStateMachine, CommandPhase


class OrbLifecycle:
    """
    Manages the Orb's process lifecycle and health probing.

    All health probes write to the state machine's RUNTIME layer.
    All status reads come from the state machine's EFFECTIVE layer.

    This ensures get_status() is pure read — it never mutates,
    never probes subsystems, just returns the last known truth.
    """

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb
        self.state_machine: CALIStateMachine = getattr(orb, "state_machine", None)

        # If CALIFloatingOrb doesn't have state_machine yet, create one
        if self.state_machine is None:
            checkout = getattr(orb, "PROJECT_ROOT", Path(__file__).parent.parent.parent.resolve())
            self.state_machine = CALIStateMachine(checkout_path=checkout)
            orb.state_machine = self.state_machine

        self._health_thread: Optional[threading.Thread] = None
        self._health_stop_event = threading.Event()
        self._health_interval = 5.0  # seconds between health probes

        # Track which subsystems we have references to
        self._audio_runtime = getattr(orb, "audio_runtime", None)
        self._tts_client = getattr(orb, "tts_client", None)
        self._voice_engine = getattr(orb, "voice_engine", None)
        self._llm_client = getattr(orb, "llm_client", None)

        # Register state change listener for debugging
        self.state_machine.add_listener(self._on_state_change)

    # ------------------------------------------------------------------
    # State Change Listener (for debug logging)
    # ------------------------------------------------------------------

    def _on_state_change(self, domain: str, event: dict):
        """Log significant state changes."""
        # Only log block events or command transitions
        if event.get("layer") == "effective" and "block_reason" in str(event):
            print(f"[OrbLifecycle] {domain} blocked: {event}", flush=True)
        elif event.get("layer") == "command":
            print(f"[OrbLifecycle] Command event: {event}", flush=True)

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self):
        """
        Start all background threads and health probing.
        Replaces CALIFloatingOrb.start()
        """
        print("[OrbLifecycle] Starting Orb lifecycle...", flush=True)

        # Mark system as alive
        self.state_machine.set_desired_state("system", {"orb_alive": True}, source="OrbLifecycle")
        self.state_machine.set_activity_state("system", {"state": "starting", "started_at": time.time()})

        # Start the background health probe thread
        self._health_stop_event.clear()
        self._health_thread = threading.Thread(
            target=self._health_probe_loop,
            daemon=True,
            name="orb-health-probe"
        )
        self._health_thread.start()

        # Set activity to running
        self.state_machine.set_activity_state("system", {"state": "running", "started_at": time.time()})
        print("[OrbLifecycle] Orb lifecycle started.", flush=True)

    def stop(self):
        """
        Graceful shutdown. Replaces CALIFloatingOrb.stop()
        """
        print("[OrbLifecycle] Stopping Orb lifecycle...", flush=True)

        self.state_machine.set_desired_state("system", {"orb_alive": False}, source="OrbLifecycle")
        self.state_machine.set_activity_state("system", {"state": "stopping", "stopped_at": time.time()})

        # Signal health thread to stop
        self._health_stop_event.set()
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=2.0)

        # Mark all subsystems as down
        self.state_machine.update_runtime_state("listening", {"mic_available": False}, source="OrbLifecycle.shutdown")
        self.state_machine.update_runtime_state("voice", {"tts_ready": False}, source="OrbLifecycle.shutdown")
        self.state_machine.update_runtime_state("cognition", {"llm_ready": False}, source="OrbLifecycle.shutdown")

        self.state_machine.set_activity_state("system", {"state": "stopped", "stopped_at": time.time()})
        print("[OrbLifecycle] Orb lifecycle stopped.", flush=True)

    # ------------------------------------------------------------------
    # Health Probe Loop (writes to RUNTIME layer only)
    # ------------------------------------------------------------------

    def _health_probe_loop(self):
        """
        Background thread: periodically probe all subsystems
        and write results to the state machine's RUNTIME layer.

        This is the ONLY place that probes subsystems.
        get_status() NEVER probes — it only reads effective state.
        """
        print("[OrbLifecycle] Health probe loop started.", flush=True)

        while not self._health_stop_event.is_set():
            try:
                self._probe_listening()
                self._probe_voice()
                self._probe_cognition()
                self._probe_presence()

                # Sleep with early exit on stop signal
                self._health_stop_event.wait(self._health_interval)

            except Exception as e:
                print(f"[OrbLifecycle] Health probe error: {e}", flush=True)
                traceback.print_exc()
                self._health_stop_event.wait(1.0)  # Brief pause on error

        print("[OrbLifecycle] Health probe loop stopped.", flush=True)

    def _probe_listening(self):
        """Probe microphone and CP3 listener status."""
        report = {"checked_at": time.time()}

        # Check audio runtime
        audio_ok = False
        mic_error = None

        if self._audio_runtime:
            try:
                status = self._audio_runtime.get_status()
                audio_ok = status.get("mic_ready", False)
                if not audio_ok:
                    mic_error = status.get("mic_error", "mic_not_ready")
            except Exception as e:
                mic_error = f"audio_runtime probe failed: {e}"
        else:
            mic_error = "audio_runtime not available"

        report["mic_available"] = audio_ok
        if mic_error:
            report["mic_error"] = mic_error

        # Check CP3 listener
        cp3_ok = False
        cp3_error = None

        voice_engine = self._voice_engine or getattr(self.orb, "voice_engine", None)
        if voice_engine:
            try:
                cp3_ok = getattr(voice_engine, "listener_ready", False)
                if not cp3_ok:
                    cp3_error = "CP3 listener not initialized"
            except Exception as e:
                cp3_error = f"voice_engine probe failed: {e}"
        else:
            cp3_error = "voice_engine not available"

        report["cp3_ready"] = cp3_ok
        if cp3_error:
            report["cp3_error"] = cp3_error

        self.state_machine.update_runtime_state("listening", report, source="OrbLifecycle.probe")

    def _probe_voice(self):
        """Probe TTS engine status."""
        report = {"checked_at": time.time()}

        tts_ok = False
        tts_error = None

        if self._tts_client:
            try:
                status = self._tts_client.get_status()
                tts_ok = status.get("ready", False)
                if not tts_ok:
                    tts_error = status.get("error", "TTS not ready")
            except Exception as e:
                tts_error = f"tts_client probe failed: {e}"
        else:
            tts_error = "tts_client not available"

        report["tts_ready"] = tts_ok
        if tts_error:
            report["tts_error"] = tts_error

        self.state_machine.update_runtime_state("voice", report, source="OrbLifecycle.probe")

    def _probe_cognition(self):
        """Probe LLM / reasoning engine status."""
        report = {"checked_at": time.time()}

        llm_ok = False
        llm_error = None

        if self._llm_client:
            try:
                # Generic health check — assumes llm_client has health method
                llm_ok = getattr(self._llm_client, "is_ready", lambda: False)()
                if not llm_ok:
                    llm_error = "LLM client not ready"
            except Exception as e:
                llm_error = f"llm_client probe failed: {e}"
        else:
            # Try to get from orb directly
            llm_client = getattr(self.orb, "llm_client", None)
            if llm_client:
                try:
                    llm_ok = getattr(llm_client, "is_ready", lambda: False)()
                    if not llm_ok:
                        llm_error = "LLM client not ready"
                except Exception as e:
                    llm_error = f"llm_client probe failed: {e}"
            else:
                llm_error = "llm_client not available"

        report["llm_ready"] = llm_ok
        if llm_error:
            report["llm_error"] = llm_error

        self.state_machine.update_runtime_state("cognition", report, source="OrbLifecycle.probe")

    def _probe_presence(self):
        """Probe desktop presence / window manager status."""
        report = {"checked_at": time.time()}

        presence_ok = True
        presence_error = None

        # Check if we have a desktop presence module
        desktop = getattr(self.orb, "desktop_presence", None)
        if desktop:
            try:
                presence_ok = getattr(desktop, "is_active", lambda: True)()
                if not presence_ok:
                    presence_error = "Desktop presence inactive"
            except Exception as e:
                presence_error = f"desktop_presence probe failed: {e}"

        report["presence_ready"] = presence_ok
        if presence_error:
            report["presence_error"] = presence_error

        self.state_machine.update_runtime_state("presence", report, source="OrbLifecycle.probe")

    # ------------------------------------------------------------------
    # Refresh Runtime Health (one-shot, for startup)
    # ------------------------------------------------------------------

    def refresh_runtime_health(self):
        """
        One-shot health refresh. Called at startup so the first
        get_status() call has real probe data instead of stale defaults.
        """
        print("[OrbLifecycle] Refreshing runtime health (one-shot)...", flush=True)
        self._probe_listening()
        self._probe_voice()
        self._probe_cognition()
        self._probe_presence()
        print("[OrbLifecycle] Runtime health refreshed.", flush=True)

    # ------------------------------------------------------------------
    # get_status — PURE READ, NO MUTATION
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """
        PURE READ. Returns the current effective state from the state machine.

        This method NEVER probes subsystems, NEVER mutates state.
        It only reads what the health probe loop has already written.

        Backward-compatible shape for existing callers.
        """
        return self.state_machine.get_status()

    def get_full_status(self) -> dict:
        """
        PURE READ. Returns the complete four-layer state dump.
        For debugging and the bridge's detailed status endpoint.
        """
        return self.state_machine.get_full_state()

    def get_diagnostic(self, domain: str = "listening") -> dict:
        """
        Deep diagnostic for a specific domain.
        Shows exactly where the break is in the pipeline.
        """
        if domain == "listening":
            return self.state_machine.diagnose_listening()
        elif domain == "command":
            # Return last command diagnostic
            recent = self.state_machine.get_recent_commands(1)
            if recent:
                return self.state_machine.diagnose_command(recent[0]["request_id"])
            return {"error": "No commands in history"}
        else:
            return {
                "desired": self.state_machine.get_desired_state(domain),
                "runtime": self.state_machine.get_runtime_state(domain),
                "effective": self.state_machine.get_effective_state(domain),
                "activity": self.state_machine.get_activity_state(domain),
            }
