#!/usr/bin/env python3
"""Electron bridge shim for CALI Orb.
Exposes CALIFloatingOrb for PythonShell usage and supports a simple stdin/stdout
message loop so the Electron bridge can coordinate readiness and queries.
"""

import json
import os
import sys
import time
import asyncio
import threading
import urllib.request
from pathlib import Path

# Fix Windows unicode stdout issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# Add SF-ORB to path for core logic
SF_ORB_PATH = PROJECT_ROOT / "SF-ORB"
if SF_ORB_PATH.exists():
    sys.path.insert(0, str(SF_ORB_PATH))
    print(f"Added SF-ORB to path: {SF_ORB_PATH}", file=sys.stderr)

# Add ACP to path (prefer ACP3, keep legacy fallback)
ACP_PATH = None
for candidate in (
    Path(os.getenv("CP3_ROOT") or os.getenv("ACP3_ROOT") or "/mnt/r/cochlear_processor_3.0"),
    PROJECT_ROOT / "modules" / "Adaptive_Cochlear_Processor_v1",
    PROJECT_ROOT / "Adaptive_Cochlear_Processor_1.0",
):
    candidate = candidate.expanduser().resolve()
    if candidate.exists():
        ACP_PATH = candidate
        sys.path.insert(0, str(candidate))
        print(f"Added ACP to path: {candidate}", file=sys.stderr)
        break

if ACP_PATH is None:
    print("⚠️ ACP module path not found", file=sys.stderr)

# --- Input/TTS integration ---
TTS_AVAILABLE = False
SPEECH_AVAILABLE = False
KokoroBaseline = None
MicCapture = None

# Try ACP3 adapter first, then legacy ACP v1 imports
try:
    from orb_acp3_adapter import MicCapture, KokoroBaseline

    SPEECH_AVAILABLE = True
    TTS_AVAILABLE = True
    print("✓ ACP3 speech/voice adapters available", file=sys.stderr)
except ImportError as acp3_error:
    print(f"⚠️ ACP3 adapter import failed: {acp3_error}", file=sys.stderr)

    try:
        from realtime.mic_capture import MicCapture

        SPEECH_AVAILABLE = True
        print("✓ Speech recognition available (legacy ACP)", file=sys.stderr)
    except ImportError as speech_error:
        print(f"⚠️ Speech recognition import failed: {speech_error}", file=sys.stderr)

    try:
        from kokoro_baseline import KokoroBaseline

        TTS_AVAILABLE = True
        print("✓ KokoroBaseline imported successfully (legacy ACP)", file=sys.stderr)
    except ImportError as tts_error:
        print(f"⚠️ KokoroBaseline import failed: {tts_error}", file=sys.stderr)

# Debug torch status
try:
    import torch

    print("✓ TORCH IS NOW AVAILABLE", file=sys.stderr)
    print(f"PyTorch version: {torch.__version__}", file=sys.stderr)
except ImportError:
    print("Torch still missing - gravity field disabled", file=sys.stderr)

from orb_controller import SF_ORB_Controller  # noqa: E402
from cali_skg import CALISKG  # noqa: E402


class CALIFloatingOrb:
    def __init__(self, project_root):
        self.project_root = Path(project_root).resolve()
        self.instance_id = os.getenv("ORB_INSTANCE_ID", "wsl").strip() or "wsl"
        self.system_root = Path(
            os.getenv("ORB_SYSTEM_ROOT", str(self.project_root))
        ).expanduser().resolve()
        self.shared_mesh_root = os.getenv("ORB_SHARED_MESH_ROOT")
        self.controller = SF_ORB_Controller()
        self.running = False
        self.last_cursor_pos = (0, 0)
        self.last_time = time.time()
        self.auto_listen = os.getenv("ORB_AUTO_LISTEN", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.speech_enabled = False
        self.speech_thread = None
        self.listen_once_thread = None
        self.speech_lock = threading.Lock()
        self.cali = None

        try:
            self.cali = CALISKG(self.system_root)
            print("✓ CALI SKG v3 online", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ CALI SKG init failed: {e}", file=sys.stderr)

        self.voice = None
        if TTS_AVAILABLE:
            try:
                print("Initializing Sovereign Voice (Kokoro)...", file=sys.stderr)
                self.voice = KokoroBaseline()
                voice_health = self.voice.get_health_status()
                print(
                    "✓ Voice Online"
                    f" ({voice_health.get('onnx_provider', 'unknown provider')})",
                    file=sys.stderr,
                )
            except Exception as e:
                print(f"Voice init failed: {e}", file=sys.stderr)

        self.mic = None
        if SPEECH_AVAILABLE:
            try:
                print("Initializing Speech Recognition...", file=sys.stderr)
                self.mic = MicCapture()
                print("✓ Speech Recognition Online", file=sys.stderr)
            except Exception as e:
                print(f"Speech recognition init failed: {e}", file=sys.stderr)

    def speak(self, text):
        if self.voice:
            try:
                result = self.voice.synthesize(text)
                return result.get("audio_path")
            except Exception as e:
                print(f"Speech error: {e}", file=sys.stderr)
        return None

    def prepare_voice(self, text, emotion="thoughtful_warm"):
        if not self.cali:
            return None
        try:
            return self.cali.speak(text, emotion)
        except Exception as e:
            print(f"CALI voice packaging error: {e}", file=sys.stderr)
            return None

    def build_voice_payload(self, text, emotion="thoughtful_warm"):
        voice_package = self.prepare_voice(text, emotion)
        audio_path = None
        if self.voice and (not self.cali or self.cali.orb_state.get("voice_active", True)):
            audio_path = self.speak(text)
        return {"text": text, "audio_path": audio_path, "voice_package": voice_package}

    def emit_spoken_text(self, text, emotion="thoughtful_warm", request_id=None):
        payload = self.build_voice_payload(text, emotion)
        self._emit(
            {
                "type": "speak_result",
                "request_id": request_id,
                "data": payload,
            }
        )
        return payload

    def reason_with_cali(self, text, context=None):
        if not self.cali:
            return None
        try:
            return self.cali.reason(text, context=context or {})
        except Exception as e:
            print(f"CALI reasoning error: {e}", file=sys.stderr)
            return None

    def research_with_cali(self, query, domains=None):
        if not self.cali:
            return None
        try:
            return asyncio.run(self.cali.research(query, domains or []))
        except Exception as e:
            print(f"CALI research error: {e}", file=sys.stderr)
            return None

    def hear_with_cali(self, audio_signal):
        if not self.cali:
            return None
        try:
            return asyncio.run(self.cali.hear(audio_signal))
        except Exception as e:
            print(f"CALI hearing error: {e}", file=sys.stderr)
            return None

    def set_cali_orb_state(self, setting, value):
        if not self.cali:
            return False
        try:
            return self.cali.set_orb_state(setting, value)
        except Exception as e:
            print(f"CALI orb state error: {e}", file=sys.stderr)
            return False

    def _emotion_from_reasoning(self, reasoning):
        if not reasoning:
            return "thoughtful_warm"
        advisory = reasoning.get("advisory_verdict", {})
        confidence = advisory.get("confidence", 0.5)
        if confidence >= 0.8:
            return "confident"
        if confidence <= 0.45:
            return "uncertain"
        if advisory.get("tension_detected"):
            return "analytical"
        return "thoughtful_warm"

    def _emit(self, payload):
        print(json.dumps(payload), flush=True)

    def start_speech_recognition(self):
        if not self.mic:
            return False
        if self.speech_thread and self.speech_thread.is_alive():
            return True

        self.speech_thread = threading.Thread(target=self._speech_loop)
        self.speech_thread.daemon = True
        self.speech_thread.start()
        return True

    def set_speech_recognition(self, enabled):
        if not self.mic:
            return False

        self.speech_enabled = bool(enabled)
        if self.speech_enabled:
            self.start_speech_recognition()

        self._emit(
            {
                "type": "listening_mode",
                "data": {"enabled": self.speech_enabled, "mode": "continuous"},
            }
        )
        return True

    def listen_once(self):
        if not self.mic or self.speech_enabled:
            return False
        if self.speech_lock.locked():
            return False
        if self.listen_once_thread and self.listen_once_thread.is_alive():
            return False

        self.listen_once_thread = threading.Thread(
            target=self._capture_speech_chunk,
            kwargs={"mode": "oneshot"},
            daemon=True,
        )
        self.listen_once_thread.start()
        return True

    def _capture_speech_chunk(self, mode="continuous"):
        if not self.mic:
            return None
        if not self.speech_lock.acquire(blocking=False):
            return None

        try:
            self._emit({"type": "listening_state", "data": {"listening": True, "mode": mode}})
            import soundfile as sf
            import tempfile

            # Record and process audio chunk
            audio_data = self.mic.record_chunk()
            cali_hearing = self.hear_with_cali(audio_data.flatten())

            # Save to temp file since processor expects a file path
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
                sf.write(temp_path, audio_data.flatten(), self.mic.sample_rate)

            try:
                transcription = self.mic.processor.hear(temp_path)

                if transcription and transcription.strip():
                    print(f"🎤 Heard: {transcription}", file=sys.stderr)

                    # Check for verbal commands
                    self._process_verbal_command(transcription)

                    # Process the speech input like a text query
                    stimulus = {
                        "type": "speech_query",
                        "content": transcription,
                        "coordinates": [0, 0],
                        "velocity": 0.0,
                    }

                    thought = self.controller.cognitively_emerge(stimulus)
                    cali_reasoning = self.reason_with_cali(
                        transcription,
                        context={"source": "speech_query", "stimulus_type": "speech_query"},
                    )
                    response_text = (
                        cali_reasoning.get("recommended_response")
                        if cali_reasoning
                        else f"I heard you say: {transcription}"
                    )
                    voice_payload = self.build_voice_payload(
                        response_text,
                        self._emotion_from_reasoning(cali_reasoning),
                    )
                    if thought:
                        pulse = thought.pulse() if hasattr(thought, "pulse") else thought

                        # Send cognitive pulse to Electron
                        response = {
                            "type": "speech_pulse",
                            "data": pulse,
                            "transcription": transcription,
                            "response_text": response_text,
                            "audio_path": voice_payload.get("audio_path"),
                            "voice_package": voice_payload.get("voice_package"),
                            "cali_reasoning": cali_reasoning,
                            "advisory_verdict": (
                                cali_reasoning.get("advisory_verdict") if cali_reasoning else None
                            ),
                            "cali_hearing": cali_hearing,
                        }
                        self._emit(response)
                    else:
                        self._emit(
                            {
                                "type": "speech_pulse",
                                "data": {},
                                "transcription": transcription,
                                "response_text": response_text,
                                "audio_path": voice_payload.get("audio_path"),
                                "voice_package": voice_payload.get("voice_package"),
                                "cali_reasoning": cali_reasoning,
                                "advisory_verdict": (
                                    cali_reasoning.get("advisory_verdict") if cali_reasoning else None
                                ),
                                "cali_hearing": cali_hearing,
                            }
                        )
                    return transcription
                return ""
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except Exception as e:
            print(f"Speech processing error: {e}", file=sys.stderr)
            time.sleep(1)
            return None
        finally:
            self._emit({"type": "listening_state", "data": {"listening": False, "mode": mode}})
            self.speech_lock.release()

    def _speech_loop(self):
        while self.running:
            if not self.speech_enabled:
                time.sleep(0.05)
                continue

            self._capture_speech_chunk(mode="continuous")
            time.sleep(0.1)

    def _process_verbal_command(self, transcription):
        """Process verbal commands starting with 'CALI'"""
        if not transcription.lower().startswith("cali"):
            return

        command = transcription.lower()[5:].strip()

        if "slow down" in command:
            # Adjust animation speed (send to Electron)
            response = {"type": "verbal_command", "command": "slow_down"}
            print(json.dumps(response), flush=True)
            self.emit_spoken_text("Slowing down")

        elif "speed up" in command:
            response = {"type": "verbal_command", "command": "speed_up"}
            print(json.dumps(response), flush=True)
            self.emit_spoken_text("Speeding up")

        elif "change color" in command:
            # Extract color if specified
            if "blue" in command:
                color = "#00ff88"
            elif "red" in command:
                color = "#ff4444"
            elif "green" in command:
                color = "#44ff44"
            else:
                color = "#00ff88"  # default glassy blue-green

            response = {
                "type": "verbal_command",
                "command": "change_color",
                "color": color,
            }
            print(json.dumps(response), flush=True)
            self.emit_spoken_text("Changing color")

        elif "increase size" in command:
            response = {"type": "verbal_command", "command": "increase_size"}
            print(json.dumps(response), flush=True)
            self.emit_spoken_text("Increasing size")

        elif "decrease size" in command:
            response = {"type": "verbal_command", "command": "decrease_size"}
            print(json.dumps(response), flush=True)
            self.emit_spoken_text("Decreasing size")

        elif "dock" in command:
            response = {"type": "verbal_command", "command": "dock_orb"}
            print(json.dumps(response), flush=True)
            self.emit_spoken_text("Docking")

        elif "front and center" in command or "launch orb" in command or "show orb" in command:
            response = {"type": "verbal_command", "command": "show_orb"}
            print(json.dumps(response), flush=True)
            self.emit_spoken_text("Front and center")

        elif "toggle orb" in command:
            response = {"type": "verbal_command", "command": "toggle_visibility"}
            print(json.dumps(response), flush=True)
            self.emit_spoken_text("Toggling")

    def stop(self):
        self.running = False
        self.speech_enabled = False
        cognitive_thread = getattr(self, "cognitive_thread", None)
        speech_thread = getattr(self, "speech_thread", None)
        listen_once_thread = getattr(self, "listen_once_thread", None)
        if cognitive_thread:
            cognitive_thread.join(timeout=1)
        if speech_thread:
            speech_thread.join(timeout=1)
        if listen_once_thread:
            listen_once_thread.join(timeout=1)
        if self.cali:
            self.cali.close()

    def process_cursor_movement(self, x, y):
        current_time = time.time()
        dx = x - self.last_cursor_pos[0]
        dy = y - self.last_cursor_pos[1]
        dt = current_time - self.last_time
        velocity = ((dx**2 + dy**2) ** 0.5) / max(dt, 0.001) if dt > 0 else 0

        self.last_cursor_pos = (x, y)
        self.last_time = current_time

        stimulus = {
            "type": "cursor_movement",
            "coordinates": [x, y],
            "velocity": min(velocity, 50.0),
            "intent": "navigation",
        }

        thought = self.controller.cognitively_emerge(stimulus)
        if thought:
            if hasattr(thought, "pulse"):
                pulse = thought.pulse()
            else:
                # Lightning bypass returns dict directly
                pulse = thought
            # Send cognitive pulse to Electron
            response = {"type": "cognitive_pulse", "data": pulse}
            print(json.dumps(response), flush=True)
            return pulse
        return None

    def _cognitive_loop(self):
        while self.running:
            # Periodic cognitive processing if needed
            time.sleep(0.1)

    def start(self):
        self.running = True
        # Start background cognitive processing
        self.cognitive_thread = threading.Thread(target=self._cognitive_loop)
        self.cognitive_thread.daemon = True
        self.cognitive_thread.start()

        # Continuous speech recognition is opt-in for the artifact overlay model.
        if self.auto_listen:
            self.set_speech_recognition(True)

    def get_status(self):
        status = {
            "instance_id": self.instance_id,
            "running": self.running,
            "controller_status": "active" if self.controller else "inactive",
            "listening_enabled": self.speech_enabled,
            "auto_listen": self.auto_listen,
            "project_root": str(self.project_root),
            "system_root": str(self.system_root),
            "shared_mesh_root": self.shared_mesh_root,
        }
        if self.cali:
            status["cali_status"] = self.cali.get_status()
        return status


__all__ = ["CALIFloatingOrb"]


def _main() -> None:
    """Run Orb and respond to simple IPC messages over stdin/stdout (JSON lines)."""
    orb = CALIFloatingOrb(PROJECT_ROOT)
    orb.start()

    # Check UCM status
    try:
        with urllib.request.urlopen(
            "http://localhost:5050/orb/status", timeout=5
        ) as response:
            data = json.loads(response.read().decode())
            if data.get("status") == "active":
                print("UCM status active", file=sys.stderr)
            else:
                print("UCM status not active", file=sys.stderr)
    except Exception as e:
        print(f"UCM status check failed: {e}", file=sys.stderr)

    # Signal readiness to Electron bridge
    print(json.dumps({"type": "ready"}), flush=True)

    for line in sys.stdin:
        try:
            msg = json.loads(line.strip())
        except Exception:
            continue

        msg_type = msg.get("type")
        request_id = msg.get("request_id")

        if msg_type == "shutdown":
            orb.stop()
            print(json.dumps({"type": "shutdown_ack", "request_id": request_id}), flush=True)
            break

        elif msg_type == "cursor_move":
            x = msg.get("x", 0)
            y = msg.get("y", 0)
            orb.process_cursor_movement(x, y)

        elif msg_type == "get_status":
            status = orb.get_status()
            response = {"type": "status_response", "request_id": request_id, "data": status}
            print(json.dumps(response), flush=True)

        elif msg_type == "listen_once":
            accepted = orb.listen_once()
            orb._emit(
                {
                    "type": "listen_once_ack",
                    "request_id": request_id,
                    "data": {"accepted": accepted},
                }
            )

        elif msg_type == "set_listening":
            enabled = bool(msg.get("enabled", False))
            ok = orb.set_speech_recognition(enabled)
            orb._emit(
                {
                    "type": "listening_mode",
                    "request_id": request_id,
                    "data": {
                        "enabled": orb.speech_enabled if ok else False,
                        "ok": ok,
                        "mode": "continuous",
                    },
                }
            )

        elif msg_type == "query":
            text = msg.get("text", "")
            # Use SF-ORB cognitive processing
            stimulus = {
                "type": "text_query",
                "content": text,
                "coordinates": [0, 0],  # dummy
                "velocity": 0.0,
            }
            result = orb.controller.cognitively_emerge(stimulus)
            cali_reasoning = orb.reason_with_cali(
                text,
                context={"source": "ipc_query", "stimulus_type": "text_query"},
            )

            response_text = (
                cali_reasoning.get("recommended_response")
                if cali_reasoning
                else f"Analyzed: {text}"
            )
            voice_payload = orb.build_voice_payload(
                response_text, orb._emotion_from_reasoning(cali_reasoning)
            )

            response = {
                "type": "query_result",
                "request_id": request_id,
                "data": {
                    "echo": text,
                    "response_text": response_text,
                    "audio_path": voice_payload.get("audio_path"),
                    "voice_package": voice_payload.get("voice_package"),
                    "cali_reasoning": cali_reasoning,
                    "advisory_verdict": (
                        cali_reasoning.get("advisory_verdict") if cali_reasoning else None
                    ),
                    "cognitive_result": (
                        result.pulse() if hasattr(result, "pulse") else result
                    ),
                    "state": orb.get_status(),
                },
            }
            print(json.dumps(response), flush=True)

        elif msg_type == "research":
            query = msg.get("query") or msg.get("text", "")
            domains = msg.get("domains") or []
            research = orb.research_with_cali(query, domains) or {
                "voice_response": "Research is unavailable right now.",
                "research_synthesis": {"error": "CALI research offline"},
            }
            voice_payload = orb.build_voice_payload(research.get("voice_response", ""))
            orb._emit(
                {
                    "type": "research_result",
                    "request_id": request_id,
                    "data": {
                        **research,
                        "voice_package": voice_payload.get("voice_package"),
                        "audio_path": voice_payload.get("audio_path"),
                    },
                }
            )

        elif msg_type == "speak":
            text = msg.get("text", "")
            emotion = msg.get("emotion", "thoughtful_warm")
            orb._emit(
                {
                    "type": "speak_result",
                    "request_id": request_id,
                    "data": orb.build_voice_payload(text, emotion),
                }
            )

        elif msg_type == "set_orb_state":
            setting = msg.get("setting")
            value = msg.get("value")
            ok = orb.set_cali_orb_state(setting, value)
            orb._emit(
                {
                    "type": "orb_state_result",
                    "request_id": request_id,
                    "data": {"ok": ok, "state": orb.get_status()},
                }
            )


if __name__ == "__main__":
    _main()
