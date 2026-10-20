"""
orb_behavior_runtime.py — Embodied ORB behavior: summon, autonomy, cursor, presence.

Extracted from floating_assistant_orb.py:
  _detect_whistle_summon(), _is_cali_summon_request(),
  _process_verbal_command(), process_cursor_movement(),
  _presence_profile_from_stimulus(), _build_presence_update(),
  _emit_presence_pulse(), _to_ratio(), _emotion_from_reasoning(),
  cognitively_emerge(), idle_cognition()

Design rule: this module owns the doctrine of HOW the orb moves and responds
to physical/audio stimuli. It does NOT own audio routing or research.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from floating_assistant_orb import CALIFloatingOrb


class OrbBehaviorRuntime:
    """
    Embodies the ORB's physical-cognitive presence:
      - Whistle summon detection (FFT-based, configurable thresholds)
      - Text summon detection ("CALI come here" etc.)
      - Verbal command processing ("CALI slow down", "CALI change color"...)
      - Cursor movement → cognitive stimulus → pulse emit
      - Presence profile derivation from desktop stimulus
      - Emotion inference from reasoning payload
      - cognitively_emerge / idle_cognition delegation to controller
    """

    def __init__(self, orb: "CALIFloatingOrb"):
        self.orb = orb
        self.state_machine = getattr(orb, "state_machine", None)
        self._last_whistle_summon_at: float = 0.0
        self.latest_presence_update: Optional[Dict] = None

    # ── Whistle summon ────────────────────────────────────────────────────────

    def detect_whistle_summon(self, audio_data: Any, sample_rate: int) -> bool:
        """
        FFT-based whistle detection.
        Returns True and emits cali_summon event if a summon whistle is detected.
        All thresholds configurable via environment variables.
        """
        try:
            import numpy as np
        except ImportError:
            return False

        try:
            cooldown = float(os.getenv("ORB_WHISTLE_SUMMON_COOLDOWN_SEC", "4.0"))
            now      = time.time()
            if now - self._last_whistle_summon_at < cooldown:
                return False

            signal = np.asarray(audio_data, dtype=np.float32).flatten()
            if signal.size < max(1024, int(sample_rate * 0.25)):
                return False

            signal  -= float(np.mean(signal))
            rms      = float(np.sqrt(np.mean(signal * signal)))
            min_rms  = float(os.getenv("ORB_WHISTLE_MIN_RMS", "0.018"))
            if rms < min_rms:
                return False

            max_samples = int(sample_rate * 1.6)
            if signal.size > max_samples:
                signal = signal[:max_samples]

            window   = np.hanning(signal.size).astype(np.float32)
            spectrum = np.abs(np.fft.rfft(signal * window))
            freqs    = np.fft.rfftfreq(signal.size, d=1.0 / float(sample_rate))
            if spectrum.size < 8:
                return False

            whistle_min = float(os.getenv("ORB_WHISTLE_MIN_HZ",  "1150"))
            whistle_max = float(os.getenv("ORB_WHISTLE_MAX_HZ",  "4200"))
            band_mask   = (freqs >= whistle_min) & (freqs <= whistle_max)
            low_mask    = (freqs >= 120) & (freqs < 950)
            if not np.any(band_mask):
                return False

            band             = spectrum[band_mask]
            peak             = float(np.max(band))
            band_sum         = float(np.sum(band)) + 1e-9
            total_sum        = float(np.sum(spectrum)) + 1e-9
            low_sum          = float(np.sum(spectrum[low_mask])) + 1e-9
            peak_freq        = float(freqs[band_mask][int(np.argmax(band))])
            tonal_ratio      = peak / band_sum
            band_energy_ratio = band_sum / total_sum
            high_to_low_ratio = band_sum / low_sum

            tonal_thresh     = float(os.getenv("ORB_WHISTLE_TONAL_RATIO",    "0.18"))
            band_thresh      = float(os.getenv("ORB_WHISTLE_BAND_RATIO",     "0.34"))
            high_low_thresh  = float(os.getenv("ORB_WHISTLE_HIGH_LOW_RATIO", "1.15"))

            if (
                tonal_ratio      >= tonal_thresh
                and band_energy_ratio >= band_thresh
                and high_to_low_ratio >= high_low_thresh
            ):
                self._last_whistle_summon_at = now
                self.orb._emit({
                    "type":   "cali_summon",
                    "source": "whistle",
                    "data":   {
                        "peak_hz":    round(peak_freq, 1),
                        "rms":        round(rms, 5),
                        "tonal_ratio": round(tonal_ratio, 4),
                    },
                })
                return True
        except Exception as exc:
            print(f"Whistle summon detection error: {exc}", file=sys.stderr)
        return False

    # ── Text summon ───────────────────────────────────────────────────────────

    def is_cali_summon_request(self, text: str) -> bool:
        """
        Returns True if the transcript is a summon phrase.
        "CALI come here", "get over here", "call cali", etc.
        """
        normalized = re.sub(r"[^\w\s]", " ", str(text or "").lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return False
        return bool(
            normalized in {"cali", "callie", "hey cali", "hey callie", "ok cali", "okay cali"}
            or re.search(r"\b(cali|callie)\b", normalized)
            or re.search(
                r"\b(cali|callie|orb|assistant)\s+(come here|come to me|over here|come back|return|come)\b",
                normalized,
            )
            or re.search(
                r"\b(come here|come to me|over here|get over here|summon cali|call cali|cali here)\b",
                normalized,
            )
        )

    def legacy_is_cali_summon_request(self, text: str) -> bool:
        normalized = re.sub(r"[^\w\s]", " ", str(text or "").lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return False
        return bool(
            re.search(
                r"\b(cali|orb|assistant)\s+(come here|come to me|over here|come back|return|come)\b",
                normalized,
            )
            or re.search(
                r"\b(come here|come to me|over here|get over here|summon cali|call cali|cali here)\b",
                normalized,
            )
        )

    # ── Verbal commands ───────────────────────────────────────────────────────

    def process_verbal_command(self, transcription: str) -> None:
        """
        Handle "CALI <command>" verbal instructions.
        Emits verbal_command events and speaks acknowledgement.
        Only processes transcriptions that begin with "cali".
        """
        if not transcription.lower().startswith("cali"):
            return
        command = transcription.lower()[5:].strip()
        orb     = self.orb

        if "slow down" in command:
            orb._emit({"type": "verbal_command", "command": "slow_down"})
            orb.emit_spoken_text("Slowing down")

        elif "speed up" in command:
            orb._emit({"type": "verbal_command", "command": "speed_up"})
            orb.emit_spoken_text("Speeding up")

        elif "change color" in command:
            color = "#00ff88"
            if "blue"  in command: color = "#00ff88"
            if "red"   in command: color = "#ff4444"
            if "green" in command: color = "#44ff44"
            orb._emit({"type": "verbal_command", "command": "change_color", "color": color})
            orb.emit_spoken_text("Changing color")

        elif "increase size" in command:
            orb._emit({"type": "verbal_command", "command": "increase_size"})
            orb.emit_spoken_text("Increasing size")

        elif "decrease size" in command:
            orb._emit({"type": "verbal_command", "command": "decrease_size"})
            orb.emit_spoken_text("Decreasing size")

        elif "dock" in command:
            orb._emit({"type": "verbal_command", "command": "dock_orb"})
            orb.emit_spoken_text("Docking")

        elif any(p in command for p in ("front and center", "launch orb", "show orb")):
            orb._emit({"type": "verbal_command", "command": "show_orb"})
            orb.emit_spoken_text("Front and center")

        elif "toggle orb" in command:
            orb._emit({"type": "verbal_command", "command": "toggle_visibility"})
            orb.emit_spoken_text("Toggling")

    # ── Cursor movement → cognitive pulse ────────────────────────────────────

    def process_cursor_movement(self, x: int, y: int) -> Optional[Dict]:
        """
        Convert cursor coords into a cognitive stimulus and emit the pulse.
        Returns the pulse dict or None if the controller is not ready.
        """
        orb          = self.orb
        if self.state_machine:
            effective = self.state_machine.get_effective_state("motion")
            if effective and not effective.get("can_move", True):
                self.state_machine.set_activity_state(
                    "motion", {"state": "cursor_ignored", "reason": "motion_disabled", "at": time.time()}
                )
                return None
            # The cursor is an input to cognition, not a motion target. Physical motion belongs to the
            # Motion runtime (renderer) and arrives through report_physical_motion().
            self.state_machine.set_activity_state(
                "motion", {"state": "cursor_observed", "cursor": [x, y], "at": time.time()}
            )
        current_time = time.time()
        last_x, last_y = getattr(orb, "last_cursor_pos", (0, 0))
        last_time    = getattr(orb, "last_time", current_time)

        dx       = x - last_x
        dy       = y - last_y
        dt       = max(current_time - last_time, 0.001)
        velocity = min(((dx ** 2 + dy ** 2) ** 0.5) / dt, 50.0)

        orb.last_cursor_pos = (x, y)
        orb.last_time       = current_time

        stimulus = {
            "type":        "cursor_movement",
            "coordinates": [x, y],
            "velocity":    velocity,
            "intent":      "navigation",
        }
        thought = self.cognitively_emerge(stimulus)
        if not thought:
            if self.state_machine:
                self.state_machine.set_activity_state(
                    "motion", {"state": "cursor_processed", "result": "no_handler", "at": time.time()}
                )
            return None

        pulse = thought.pulse() if hasattr(thought, "pulse") else thought
        if isinstance(pulse, dict):
            pulse["field_density"]  = getattr(thought, "logic_validity", {}).get("field_density", 0)
            ucm   = getattr(thought, "ucm_envelope", None) or {}
            flags = (ucm.get("cali_reflection") or {}).get("flags", {})
            pulse["drift_detected"] = flags.get("drift_detected", False)
            if getattr(thought, "epistemic_traces", None):
                pulse["four_mind"] = {
                    mind: round(data.get("confidence", 0.5), 3)
                    for mind, data in thought.epistemic_traces.items()
                }
            pulse["egf_state"] = getattr(thought, "egf_visual_state", None)

        orb._emit({"type": "cognitive_pulse", "data": pulse})
        egf = (pulse or {}).get("egf_state") if isinstance(pulse, dict) else None
        if isinstance(egf, dict):
            orb._emit({"type": "egf_state", "data": egf})

        if self.state_machine:
            self.state_machine.set_activity_state(
                "motion", {"state": "cursor_processed", "result": "success", "at": time.time()}
            )
        return pulse

    # ── Cognitive emergence ───────────────────────────────────────────────────

    def cognitively_emerge(self, stimulus: Dict) -> Any:
        """Route stimulus through controller. Emit presence pulse if applicable."""
        if self.state_machine:
            effective = self.state_machine.get_effective_state("cognition")
            if effective and not effective.get("want_cognition", True):
                self.state_machine.set_activity_state(
                    "cognition",
                    {"state": "blocked", "reason": "cognition_disabled"},
                    source="OrbBehaviorRuntime",
                )
                return None
            self.state_machine.set_activity_state(
                "cognition",
                {"state": "emerging", "stimulus_type": (stimulus or {}).get("type"), "started_at": time.time()},
                source="OrbBehaviorRuntime",
            )
        if not self.orb.controller:
            return None
        thought = self.orb.controller.cognitively_emerge(stimulus)
        self._emit_presence_pulse(stimulus, thought)
        if self.state_machine:
            self.state_machine.set_activity_state(
                "cognition",
                {"state": "emerged", "completed_at": time.time()},
                source="OrbBehaviorRuntime",
            )
        return thought

    def idle_cognition(self, stimulus: Dict) -> Any:
        """Route idle stimulus through controller."""
        orb = self.orb
        if not orb.controller:
            return None
        thought = (
            orb.controller.idle_cognition(stimulus)
            if hasattr(orb.controller, "idle_cognition")
            else orb.controller.cognitively_emerge(stimulus)
        )
        self._emit_presence_pulse(stimulus, thought)
        return thought

    # ── Presence pulse emission ───────────────────────────────────────────────

    def _emit_presence_pulse(self, stimulus: Dict, thought: Any) -> None:
        stype = str((stimulus or {}).get("type", ""))
        if stype not in {"desktop_context", "idle_transition", "idle_reflection"}:
            return
        cognitive = None
        if thought is not None:
            try:
                cognitive = thought.pulse() if hasattr(thought, "pulse") else thought
            except Exception:
                cognitive = None
        update = self._build_presence_update(stimulus, cognitive)
        self.latest_presence_update = update
        self.orb._emit(update)
        # Propagate to orb for get_status() visibility
        self.orb.latest_presence_update = update

    def _build_presence_update(
        self, stimulus: Dict, cognitive: Optional[Dict]
    ) -> Dict[str, Any]:
        payload  = stimulus or {}
        context  = payload.get("presence_context") or {}
        meta     = payload.get("meta") or {}
        profile  = self._presence_profile_from_stimulus(payload)
        advisory = (cognitive or {}).get("advisory_verdict", {}) if isinstance(cognitive, dict) else {}

        confidence = advisory.get("confidence")
        if confidence is None and isinstance(cognitive, dict):
            confidence = cognitive.get("confidence")
        if confidence is None:
            confidence = profile.get("autonomy_level", 0.82)

        event_name = str(meta.get("event") or payload.get("type") or "presence")
        if event_name == "desktop_context":
            event_name = "context_update"

        return {
            "type":             "presence_update",
            "schema_version":   "1.0",
            "ts":               float(context.get("timestamp") or time.time()),
            "idle":             bool(profile.get("is_idle")),
            "idle_seconds":     int(profile.get("idle_seconds") or 0),
            "active_window":    str(context.get("active_window") or "unknown"),
            "active_process":   str(context.get("active_process") or "unknown"),
            "cpu":              self._to_ratio(context.get("system_load"),   fallback=0.0),
            "memory":           self._to_ratio(context.get("memory_usage"),  fallback=0.0),
            "cognitive_mode":   str((cognitive or {}).get("cognitive_mode", "DEDUCTIVE")) if isinstance(cognitive, dict) else "DEDUCTIVE",
            "autonomy_level":   float(profile.get("autonomy_level") or 0.82),
            "confidence_state": max(0.0, min(1.0, float(confidence))),
            "last_event":       event_name,
            "quadrant":         context.get("quadrant"),
            "stimulus_type":    str(payload.get("type") or ""),
            "cursor_influence": profile.get("cursor_influence"),
            "movement_intent":  profile.get("movement_intent"),
        }

    # ── Presence profile ──────────────────────────────────────────────────────

    def _presence_profile_from_stimulus(self, stimulus: Dict) -> Dict[str, Any]:
        """
        Derive autonomy level, cursor influence, and movement intent from stimulus.
        Idle stimuli get higher autonomy (0.94) and freer movement.
        """
        payload      = stimulus or {}
        context      = payload.get("presence_context") or {}
        meta         = payload.get("meta") or {}
        event        = str(meta.get("event") or "").lower()
        idle_seconds = int(context.get("idle_seconds") or meta.get("idle_seconds") or 0)
        is_idle      = (
            payload.get("type") == "idle_reflection"
            or event == "idle_start"
            or idle_seconds >= 30
        )
        return {
            "is_idle":          is_idle,
            "idle_seconds":     idle_seconds,
            "autonomy_level":   0.94 if is_idle else 0.82,
            "cursor_influence": "minimal" if is_idle else "low",
            "movement_intent":  "free_float",
            "quadrant":         context.get("quadrant"),
            "active_process":   context.get("active_process"),
            "active_window":    context.get("active_window"),
        }

    # ── Emotion inference ─────────────────────────────────────────────────────

    def emotion_from_reasoning(self, reasoning: Optional[Dict]) -> str:
        """Map CALI reasoning payload to a TTS emotion string."""
        if not reasoning:
            return "thoughtful_warm"
        advisory   = reasoning.get("advisory_verdict", {})
        confidence = advisory.get("confidence", 0.5)
        if confidence >= 0.8:
            return "confident"
        if confidence <= 0.45:
            return "uncertain"
        if advisory.get("tension_detected"):
            return "analytical"
        return "thoughtful_warm"

    # ── Ratio helper ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_ratio(raw_value: Any, fallback: float = 0.0) -> float:
        """Normalise a value to [0.0, 1.0]. Handles percentages (> 1.0)."""
        try:
            numeric = float(raw_value)
        except Exception:
            return float(fallback)
        if numeric > 1.0:
            numeric /= 100.0
        return max(0.0, min(1.0, numeric))
