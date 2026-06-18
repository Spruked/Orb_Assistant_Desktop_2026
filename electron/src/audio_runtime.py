#!/usr/bin/env python3
"""Audio runtime: native hearing plus optional local Kokoro voice."""

from __future__ import annotations

import os
import json
import subprocess
import sys
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Audio adapter import state
# ---------------------------------------------------------------------------

AUDIO_IMPORT_STATUS = "pending"
AUDIO_IMPORT_ERROR = ""
_AUDIO_IMPORT_ATTEMPTED = False
_AUDIO_IMPORT_LOCK = threading.Lock()

TTS_AVAILABLE = False
SPEECH_AVAILABLE = False

KokoroBaseline = None
MicCapture = None


def _preferred_tts_provider():
    return (
        os.getenv("ORB_TTS_PROVIDER")
        or os.getenv("ORB_PRIMARY_TTS_PROVIDER")
        or os.getenv("ORB_REALTIME_TTS_ENGINE")
        or "cosyvoice-stream"
    ).strip().lower()


def _uses_local_kokoro_voice():
    if os.getenv("ORB_ENABLE_KOKORO_FALLBACK", "1").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    return _preferred_tts_provider() == "kokoro"


def _win_path_to_wsl(path_value):
    raw = str(path_value or "")
    if len(raw) >= 3 and raw[1] == ":" and raw[2] in {"\\", "/"}:
        drive = raw[0].lower()
        rest = raw[3:].replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return raw.replace("\\", "/")


def _wsl_faster_whisper_python():
    candidate = (
        os.getenv("ORB_REALTIME_STT_PYTHON")
        or os.getenv("ORB_WSL_FASTER_WHISPER_PYTHON")
        or "/home/bryan/venv312/bin/python"
    ).strip()
    return candidate if candidate.startswith("/") else ""


def _can_use_wsl_faster_whisper():
    return bool(_wsl_faster_whisper_python()) and os.name == "nt"


# ---------------------------------------------------------------------------
# Native Kokoro TTS
# ---------------------------------------------------------------------------

class NativeKokoroBaseline:
    """Native local Kokoro voice runtime."""

    def __init__(self):
        self.voice = os.getenv("KOKORO_DEFAULT_VOICE", "af_bella").strip() or "af_bella"
        self.speed = float(os.getenv("KOKORO_DEFAULT_SPEED", "1.03"))
        self.lang_code = (
            os.getenv("KOKORO_DEFAULT_LANG_CODE", self.voice[:1]).strip()
            or self.voice[:1]
        )

        self.audio_dir = Path(os.getenv("KOKORO_AUDIO_DIR", "CALI_System/voice_cache"))
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.kokoro_root = Path(
            os.getenv(
                "KOKORO_ENGINE_ROOT",
                r"R:\R_Drive_Substrate\Services\kokoro_engine",
            )
        )

        if self.kokoro_root.exists() and str(self.kokoro_root) not in sys.path:
            sys.path.insert(0, str(self.kokoro_root))

        from kokoro import KPipeline

        self.pipeline = KPipeline(lang_code=self.lang_code)

    def synthesize(
        self,
        text,
        speaker_id="desktop",
        orb_id="desktop",
        intelligence_provider="llama3.2:1b",
    ):
        output_path = (
            self.audio_dir
            / f"kokoro_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"
        )

        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)

            for result in self.pipeline(
                str(text or ""),
                voice=self.voice,
                speed=self.speed,
                split_pattern=r"\n+",
            ):
                audio = getattr(result, "audio", None)
                if audio is None:
                    continue

                audio_array = (
                    audio.detach().cpu().numpy()
                    if hasattr(audio, "detach")
                    else np.asarray(audio)
                )

                audio_bytes = (audio_array * 32767).astype(np.int16).tobytes()
                wav_file.writeframes(audio_bytes)

        return {
            "audio_path": str(output_path),
            "voice": self.voice,
            "provider": "kokoro",
            "speaker_id": speaker_id,
            "orb_id": orb_id,
            "intelligence_provider": intelligence_provider,
        }


# ---------------------------------------------------------------------------
# Native text framing
# ---------------------------------------------------------------------------

def frame_text_input(text, context=None, speaker_id="orb_operator"):
    """Frame user text input before cognition/LLM handling."""
    return {
        "text": str(text or ""),
        "context": context or {},
        "speaker_id": speaker_id,
        "frame_provider": "orb_native_text_frame",
    }


# ---------------------------------------------------------------------------
# Faster-Whisper ASR
# ---------------------------------------------------------------------------

class FasterWhisperProcessor:
    """Local Faster-Whisper transcription processor."""

    def __init__(self):
        self.model_name = (
            os.getenv("FASTER_WHISPER_MODEL")
            or os.getenv("WHISPER_MODEL")
            or "tiny"
        ).strip() or "tiny"

        requested_device = (
            os.getenv("FASTER_WHISPER_DEVICE")
            or os.getenv("WHISPER_DEVICE")
            or "cpu"
        ).strip().lower()

        self.device = "cpu" if requested_device in {"", "auto"} else requested_device

        self.compute_type = (
            os.getenv("FASTER_WHISPER_COMPUTE_TYPE", "int8").strip()
            or "int8"
        )

        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )

        return self._model

    def hear(self, audio_path, context=None):
        model = self._load_model()

        segments, info = model.transcribe(
            str(audio_path),
            beam_size=1,
            vad_filter=False,
        )

        transcript = " ".join(
            str(segment.text or "").strip()
            for segment in segments
        ).strip()

        return {
            "transcript": transcript,
            "backend": "faster_whisper",
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": getattr(info, "language", None),
            "context": context or {},
        }

    def get_model_info(self):
        return {
            "model_name": self.model_name,
            "asr_backend": "faster_whisper",
            "asr_backend_details": {
                "name": "faster_whisper",
                "whisper_available": True,
                "whisper_model": self.model_name,
                "whisper_device": self.device,
                "compute_type": self.compute_type,
            },
        }


class WSLFasterWhisperProcessor:
    """Transcribe Windows-captured WAV files through faster-whisper in WSL."""

    def __init__(self):
        self.python = _wsl_faster_whisper_python()
        self.model_name = (
            os.getenv("FASTER_WHISPER_MODEL")
            or os.getenv("WHISPER_MODEL")
            or "tiny"
        ).strip() or "tiny"
        self.device = (
            os.getenv("FASTER_WHISPER_DEVICE")
            or os.getenv("WHISPER_DEVICE")
            or "cpu"
        ).strip().lower() or "cpu"
        if self.device == "auto":
            self.device = "cpu"
        self.compute_type = (
            os.getenv("FASTER_WHISPER_COMPUTE_TYPE", "int8").strip()
            or "int8"
        )

    def hear(self, audio_path, context=None):
        wsl_audio_path = _win_path_to_wsl(audio_path)
        code = r"""
import json
import sys
from faster_whisper import WhisperModel

audio_path, model_name, device, compute_type = sys.argv[1:5]
model = WhisperModel(model_name, device=device, compute_type=compute_type)
segments, info = model.transcribe(audio_path, beam_size=1, vad_filter=False)
transcript = " ".join(str(segment.text or "").strip() for segment in segments).strip()
print(json.dumps({
    "transcript": transcript,
    "backend": "faster_whisper",
    "runtime": "wsl",
    "model": model_name,
    "device": device,
    "compute_type": compute_type,
    "language": getattr(info, "language", None),
}))
"""
        proc = subprocess.run(
            [
                "wsl.exe",
                "-e",
                self.python,
                "-c",
                code,
                wsl_audio_path,
                self.model_name,
                self.device,
                self.compute_type,
            ],
            capture_output=True,
            text=True,
            timeout=int(os.getenv("ORB_WSL_FASTER_WHISPER_TIMEOUT_SEC", "120")),
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "").strip())
        payload = json.loads((proc.stdout or "{}").strip())
        payload["context"] = context or {}
        return payload

    def get_model_info(self):
        return {
            "model_name": self.model_name,
            "asr_backend": "faster_whisper",
            "asr_backend_details": {
                "name": "faster_whisper",
                "runtime": "wsl",
                "whisper_available": True,
                "whisper_model": self.model_name,
                "whisper_device": self.device,
                "compute_type": self.compute_type,
                "python": self.python,
            },
        }


class FasterWhisperMicCapture:
    """Sounddevice microphone capture feeding Faster-Whisper."""

    def __init__(self):
        import sounddevice as sd

        self.sd = sd
        self.sample_rate = int(os.getenv("ORB_MIC_SAMPLE_RATE", "16000"))
        self.channels = int(os.getenv("ORB_MIC_CHANNELS", "1"))
        self.chunk_seconds = float(os.getenv("ORB_MIC_CHUNK_SECONDS", "4"))
        self.processor = (
            WSLFasterWhisperProcessor()
            if _can_use_wsl_faster_whisper()
            else FasterWhisperProcessor()
        )

    def record_chunk(self):
        frames = max(1, int(self.sample_rate * self.chunk_seconds))

        audio = self.sd.rec(
            frames,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
        )

        self.sd.wait()
        return audio

    def get_status(self):
        return {
            "backend": "sounddevice",
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "chunk_seconds": self.chunk_seconds,
            "asr_backend": "faster_whisper",
            "asr_backend_details": self.processor.get_model_info()[
                "asr_backend_details"
            ],
        }


# ---------------------------------------------------------------------------
# Audio adapter loading
# ---------------------------------------------------------------------------

def _load_audio_adapters():
    global AUDIO_IMPORT_STATUS, AUDIO_IMPORT_ERROR, _AUDIO_IMPORT_ATTEMPTED
    global SPEECH_AVAILABLE, TTS_AVAILABLE, KokoroBaseline, MicCapture

    with _AUDIO_IMPORT_LOCK:
        if _AUDIO_IMPORT_ATTEMPTED:
            return

        _AUDIO_IMPORT_ATTEMPTED = True
        AUDIO_IMPORT_STATUS = "loading"
        AUDIO_IMPORT_ERROR = ""

        speech_ok = False
        voice_ok = False
        errors = []

        try:
            import sounddevice  # noqa: F401

            if _can_use_wsl_faster_whisper():
                proc = subprocess.run(
                    [
                        "wsl.exe",
                        "-e",
                        _wsl_faster_whisper_python(),
                        "-c",
                        "import faster_whisper",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if proc.returncode != 0:
                    raise RuntimeError((proc.stderr or proc.stdout or "").strip())
            else:
                import faster_whisper  # noqa: F401

            MicCapture = FasterWhisperMicCapture
            SPEECH_AVAILABLE = True
            speech_ok = True
        except Exception as speech_exc:
            MicCapture = None
            SPEECH_AVAILABLE = False
            errors.append(f"speech_unavailable:{speech_exc}")

        if _uses_local_kokoro_voice():
            try:
                kokoro_root = Path(
                    os.getenv(
                        "KOKORO_ENGINE_ROOT",
                        r"R:\R_Drive_Substrate\Services\kokoro_engine",
                    )
                )

                if kokoro_root.exists() and str(kokoro_root) not in sys.path:
                    sys.path.insert(0, str(kokoro_root))

                import kokoro  # noqa: F401

                KokoroBaseline = NativeKokoroBaseline
                TTS_AVAILABLE = True
                voice_ok = True
            except Exception as voice_exc:
                KokoroBaseline = None
                TTS_AVAILABLE = False
                errors.append(f"kokoro_unavailable:{voice_exc}")
        else:
            KokoroBaseline = None
            TTS_AVAILABLE = False

        AUDIO_IMPORT_STATUS = "online" if speech_ok or voice_ok else "unavailable"
        AUDIO_IMPORT_ERROR = "; ".join(errors)


def ensure_audio_adapters():
    """Ensure native audio adapters are loaded."""
    if not _AUDIO_IMPORT_ATTEMPTED:
        _load_audio_adapters()

    return AUDIO_IMPORT_STATUS == "online"


def get_adapter_state():
    """Return current audio adapter state."""
    return {
        "runtime": "faster_whisper_native",
        "legacy_processor_removed": True,
        "adapter_import_status": AUDIO_IMPORT_STATUS,
        "adapter_import_error": AUDIO_IMPORT_ERROR,
        "speech_adapter_available": MicCapture is not None,
        "voice_adapter_available": KokoroBaseline is not None,
        "text_framing_available": True,
        "asr_backend": "faster_whisper" if MicCapture is not None else "unavailable",
        "tts_backend": "kokoro" if KokoroBaseline is not None else _preferred_tts_provider(),
    }


# ---------------------------------------------------------------------------
# Audio runtime manager
# ---------------------------------------------------------------------------

class AudioRuntime:
    """Runtime manager for local voice output and microphone transcription."""

    def __init__(self, project_root, instance_id="desktop"):
        self.project_root = Path(project_root)
        self.instance_id = instance_id
        self.voice = None
        self.mic = None

        self.audio_runtime_status = {
            "adapters": AUDIO_IMPORT_STATUS,
            "voice": "unavailable",
            "speech": "pending",
            "tts_provider": _preferred_tts_provider(),
            "realtime_tts_endpoint": os.getenv("ORB_REALTIME_TTS_BASE_URL"),
            "tts_fallback_used": False,
            "qwen_tts_endpoint": None,
            "tts_primary_error": "",
            "asr_backend": "faster_whisper",
            "legacy_processor_removed": True,
            "adapter_import_error": "",
        }

        self._audio_runtime_thread = None

    def _ensure_audio_adapters(self):
        if not _AUDIO_IMPORT_ATTEMPTED:
            self.audio_runtime_status["adapters"] = "loading"
            _load_audio_adapters()

        self.audio_runtime_status["adapters"] = AUDIO_IMPORT_STATUS
        self.audio_runtime_status["adapter_import_error"] = AUDIO_IMPORT_ERROR

        return AUDIO_IMPORT_STATUS == "online"

    def ensure_voice_runtime(self):
        self._ensure_audio_adapters()

        if self.voice:
            return True

        if not _uses_local_kokoro_voice():
            self.audio_runtime_status["voice"] = "external"
            self.audio_runtime_status["tts_provider"] = _preferred_tts_provider()
            self.audio_runtime_status["realtime_tts_endpoint"] = os.getenv("ORB_REALTIME_TTS_BASE_URL")
            return False

        if not TTS_AVAILABLE or KokoroBaseline is None:
            self.audio_runtime_status["voice"] = "unavailable"
            return False

        try:
            self.audio_runtime_status["voice"] = "loading"
            self.voice = KokoroBaseline()
            self.audio_runtime_status["voice"] = "online"
            self.audio_runtime_status["tts_provider"] = "kokoro"
            return True
        except Exception as exc:
            self.audio_runtime_status["voice"] = "error"
            self.audio_runtime_status["tts_primary_error"] = str(exc)
            return False

    def ensure_mic_runtime(self):
        self._ensure_audio_adapters()

        if self.mic:
            return True

        if not SPEECH_AVAILABLE or MicCapture is None:
            self.audio_runtime_status["speech"] = "unavailable"
            return False

        try:
            self.audio_runtime_status["speech"] = "loading"
            self.mic = MicCapture()
            self.audio_runtime_status["speech"] = "online"
            return True
        except Exception as exc:
            self.audio_runtime_status["speech"] = "error"
            self.audio_runtime_status["adapter_import_error"] = str(exc)
            return False

    def init_audio_runtime(self, preload=False):
        if preload and (
            self._audio_runtime_thread is None
            or not self._audio_runtime_thread.is_alive()
        ):
            self._audio_runtime_thread = threading.Thread(
                target=self._init_audio_runtime_sync,
                name="orb-faster-whisper-runtime",
                daemon=True,
            )
            self._audio_runtime_thread.start()
            return

        self._init_audio_runtime_sync()

    def _init_audio_runtime_sync(self):
        self._ensure_audio_adapters()

        if self.audio_runtime_status.get("voice") != "online":
            self.audio_runtime_status["voice"] = (
                "ready" if TTS_AVAILABLE else ("external" if not _uses_local_kokoro_voice() else "unavailable")
            )

        self.audio_runtime_status["speech"] = (
            "ready" if SPEECH_AVAILABLE else "unavailable"
        )

    def get_status(self):
        return dict(self.audio_runtime_status)

    def get_voice(self):
        return self.voice

    def get_mic(self):
        return self.mic
