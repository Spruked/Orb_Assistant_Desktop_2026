#!/usr/bin/env python3
"""TTS client: Qwen primary with Kokoro backup; CosyVoice is optional realtime."""

import base64
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import audio_runtime


def _active_realtime_tts_endpoint():
    return (
        os.getenv("ORB_REALTIME_TTS_BASE_URL")
        or os.getenv("ORB_REALTIME_TTS_ENDPOINT")
        or os.getenv("ORB_QWEN_TTS_ENDPOINT")
        or os.getenv("QWEN_TTS_ENDPOINT")
        or os.getenv("CALI_TTS_BRIDGE_URL")
        or "http://127.0.0.1:8020"
    ).rstrip("/")


def _active_qwen_tts_endpoint():
    return (
        os.getenv("ORB_QWEN_TTS_ENDPOINT")
        or os.getenv("QWEN_TTS_ENDPOINT")
        or os.getenv("CALI_TTS_BRIDGE_URL")
        or "http://127.0.0.1:8031"
    ).rstrip("/")


def _qwen_tts_endpoints():
    endpoints = []
    for value in (
        _active_qwen_tts_endpoint(),
        os.getenv("ORB_QWEN_TTS_FALLBACK_ENDPOINT"),
        os.getenv("QWEN_TTS_FALLBACK_ENDPOINT"),
        "http://127.0.0.1:8020",
    ):
        endpoint = str(value or "").strip().rstrip("/")
        if endpoint and endpoint not in endpoints:
            endpoints.append(endpoint)
    return endpoints


def _preferred_tts_provider():
    return (
        os.getenv("ORB_TTS_PROVIDER")
        or os.getenv("ORB_PRIMARY_TTS_PROVIDER")
        or os.getenv("ORB_REALTIME_TTS_ENGINE")
        or "cosyvoice-stream"
    ).strip().lower()


def _probe_qwen_tts_health(endpoint=None, provider=None):
    endpoint = (endpoint or _active_realtime_tts_endpoint()).rstrip("/")
    provider = (provider or _preferred_tts_provider()).strip().lower()
    probes = ["/health", "/status", "/"]
    tts_routes = {"/synthesize", "/tts", "/speak", "/api/synthesize", "/generate"}
    last_error = ""
    status_code = 0
    healthy_http = False
    health_payload = {}
    for route in probes:
        url = urljoin(f"{endpoint}/", route.lstrip("/"))
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=1.5) as res:
                status_code = int(getattr(res, "status", 0) or 0)
                raw_body = res.read().decode("utf-8", errors="replace")
                try:
                    health_payload = json.loads(raw_body or "{}")
                except Exception:
                    health_payload = {}
                if 200 <= status_code < 300:
                    healthy_http = True
                    break
        except Exception as exc:
            last_error = str(exc)
            continue

    if not healthy_http:
        return {
            "ready": False,
            "endpoint": endpoint,
            "provider": provider,
            "status_code": status_code,
            "error": last_error,
        }

    if health_payload.get("bridge") == "dandy_qwen_tts":
        if str(health_payload.get("status") or "").lower() != "ok":
            return {
                "ready": False,
                "endpoint": endpoint,
                "provider": provider,
                "status_code": status_code or 200,
                "error": health_payload.get("error") or "qwen_backend_degraded",
                "backend_url": health_payload.get("backend_url"),
                "backend_mode": health_payload.get("backend_mode"),
            }
        if health_payload.get("backend_qwen_ready") is False:
            return {
                "ready": False,
                "endpoint": endpoint,
                "provider": provider,
                "status_code": status_code or 200,
                "error": "qwen_backend_not_verified",
                "backend_url": health_payload.get("backend_url"),
                "backend_mode": health_payload.get("backend_mode"),
            }

    try:
        openapi_url = urljoin(f"{endpoint}/", "openapi.json")
        req = urllib.request.Request(openapi_url, method="GET")
        with urllib.request.urlopen(req, timeout=1.8) as res:
            payload = json.loads(res.read().decode("utf-8", errors="replace") or "{}")
        paths = set((payload.get("paths") or {}).keys())
        if any(route in paths for route in tts_routes):
            return {
                "ready": True,
                "endpoint": endpoint,
                "provider": provider,
                "status_code": status_code or 200,
                "error": "",
                "backend_url": health_payload.get("backend_url"),
                "backend_mode": health_payload.get("backend_mode"),
            }
        return {
            "ready": False,
            "endpoint": endpoint,
            "provider": provider,
            "status_code": status_code or 200,
            "error": "no_tts_synthesis_routes",
            "backend_url": health_payload.get("backend_url"),
            "backend_mode": health_payload.get("backend_mode"),
        }
    except Exception as exc:
        # Some runtime bridges do not expose OpenAPI but are still healthy.
        if healthy_http and "qwen3-tts" in str(health_payload.get("model", "")).lower():
            return {
                "ready": True,
                "endpoint": endpoint,
                "provider": provider,
                "status_code": status_code or 200,
                "error": "",
                "backend_url": health_payload.get("backend_url"),
                "backend_mode": health_payload.get("backend_mode"),
            }
        return {
            "ready": True,
            "endpoint": endpoint,
            "provider": provider,
            "status_code": status_code or 200,
            "error": f"openapi_probe_skipped:{exc}",
            "backend_url": health_payload.get("backend_url"),
            "backend_mode": health_payload.get("backend_mode"),
        }


def _linux_to_unc_path(path_value):
    raw = str(path_value or "").strip()
    if not raw.startswith("/"):
        return raw
    distro = os.getenv("ORB_WSL_DISTRO", "Ubuntu")
    segments = [segment for segment in raw.split("/") if segment]
    return "\\\\" + f"wsl.localhost\\{distro}\\" + "\\".join(segments)


def _extract_windows_path(path_value):
    raw = str(path_value or "")
    match = re.search(r"([A-Za-z]:\\[^\\/:*?\"<>|\r\n]+(?:\\[^\\/:*?\"<>|\r\n]+)*)", raw)
    return match.group(1) if match else None


def _build_audio_data_url(audio_path):
    try:
        audio_bytes = Path(audio_path).read_bytes()
    except Exception:
        return None
    suffix = Path(audio_path).suffix.lower()
    mime = "audio/mpeg" if suffix in {".mp3", ".mpeg"} else "audio/wav"
    return f"data:{mime};base64,{base64.b64encode(audio_bytes).decode('ascii')}"


def _save_audio_bytes(audio_bytes, project_root=".", instance_id="desktop", prefix="qwen3"):
    if not audio_bytes:
        return None
    audio_dir = Path(project_root) / "CALI_System" / "voice_cache"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_path = audio_dir / f"{prefix}_{instance_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"
    output_path.write_bytes(audio_bytes)
    return str(output_path)


def _resolve_audio_path_from_qwen(payload, project_root, instance_id="wsl"):
    if not isinstance(payload, dict):
        return None, None
    direct = (
        payload.get("audio_path")
        or payload.get("path")
        or payload.get("audio_file")
        or payload.get("output_path")
        or (payload.get("data") or {}).get("audio_path")
        or (payload.get("output") or {}).get("audio_path")
    )
    if direct:
        raw_direct = str(direct).strip()
        windows_path = _extract_windows_path(raw_direct)
        if windows_path and Path(windows_path).exists():
            return windows_path, _build_audio_data_url(windows_path)
        if Path(raw_direct).exists():
            return raw_direct, _build_audio_data_url(raw_direct)
        unc_path = _linux_to_unc_path(raw_direct)
        if unc_path and Path(unc_path).exists():
            return unc_path, _build_audio_data_url(unc_path)
        if windows_path:
            return windows_path, None
        if unc_path:
            return unc_path, None
        return raw_direct, None
    b64_audio = (
        payload.get("audio_base64")
        or (payload.get("data") or {}).get("audio_base64")
        or (payload.get("output") or {}).get("audio_base64")
    )
    if not b64_audio:
        return None, None
    try:
        voice_cache = Path(project_root) / "CALI_System" / "voice_cache"
        voice_cache.mkdir(parents=True, exist_ok=True)
        out_path = voice_cache / f"qwen_tts_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"
        audio_bytes = base64.b64decode(b64_audio)
        out_path.write_bytes(audio_bytes)
        data_url = f"data:audio/wav;base64,{base64.b64encode(audio_bytes).decode('ascii')}"
        return str(out_path), data_url
    except Exception as exc:
        print(f"Qwen audio base64 decode failed: {exc}", file=sys.stderr)
        return None, None


def _speak_with_realtime_tts(text, instance_id="wsl", active_local_model="llama3.2:1b", project_root=".", endpoint=None, provider=None):
    endpoint = (endpoint or _active_realtime_tts_endpoint()).rstrip("/")
    provider = (provider or _preferred_tts_provider()).strip().lower()
    # Cold-start guard: give the resident real-time bridge a short chance to come online.
    health = _probe_qwen_tts_health(endpoint=endpoint, provider=provider)
    warmup_wait_sec = float(os.getenv("ORB_REALTIME_TTS_WARMUP_WAIT_SEC", os.getenv("ORB_QWEN_TTS_WARMUP_WAIT_SEC", "2")))
    if not health.get("ready") and warmup_wait_sec > 0:
        import time
        deadline = time.time() + max(0.0, warmup_wait_sec)
        while time.time() < deadline:
            time.sleep(0.6)
            health = _probe_qwen_tts_health(endpoint=endpoint, provider=provider)
            if health.get("ready"):
                break
    if not health.get("ready") and provider not in {"qwen", "qwen3", "qwen-tts", "qwen3-tts"}:
        return {
            "success": False,
            "audio_path": None,
            "audio_url": None,
            "tts_provider": provider,
            "tts_fallback_used": False,
            "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
            "realtime_tts_endpoint": endpoint,
            "cp3_invoked": False,
            "tts_primary_error": health.get("error") or "unreachable",
            "audio_error": f"realtime_tts_not_ready:{health.get('error') or 'unreachable'}",
        }
    body = {
        "text": text,
        "speaker": os.getenv("ORB_REALTIME_TTS_VOICE", os.getenv("ORB_QWEN_TTS_SPEAKER", "cali")),
        "speaker_id": instance_id,
        "voice_id": os.getenv("ORB_REALTIME_TTS_VOICE", os.getenv("KOKORO_DEFAULT_VOICE", "cali")),
        "voice": os.getenv("ORB_REALTIME_TTS_VOICE", os.getenv("KOKORO_DEFAULT_VOICE", "cali")),
        "format": "wav",
        "sample_rate": 24000,
        "orb_id": instance_id,
        "intelligence_provider": active_local_model,
    }
    generate_body = {
        "text": text,
        "instruct": os.getenv(
            "ORB_QWEN_TTS_INSTRUCT",
            "A clear younger adult female voice with a warm, bright, natural tone.",
        ),
    }
    last_error = ""
    timeout_sec = float(os.getenv("ORB_REALTIME_TTS_TIMEOUT_SEC", os.getenv("ORB_QWEN_TTS_TIMEOUT_SEC", "120")))
    routes = (
        ("/speak", "/generate", "/synthesize", "/tts", "/api/synthesize", "")
        if provider in {"qwen", "qwen3", "qwen-tts", "qwen3-tts"}
        else ("/generate", "/synthesize", "/tts", "/speak", "/api/synthesize", "")
    )
    for route in routes:
        route_body = generate_body if route == "/generate" else body
        payload = json.dumps(route_body).encode("utf-8")
        target = urljoin(f"{endpoint}/", route.lstrip("/"))
        req = urllib.request.Request(
            target,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as res:
                status_code = int(getattr(res, "status", 0) or 0)
                content_type = str(res.headers.get("Content-Type", "") or "").lower()
                raw_bytes = res.read()
            if "audio/" in content_type or raw_bytes.startswith(b"RIFF"):
                audio_path = _save_audio_bytes(raw_bytes, project_root, instance_id, prefix="qwen3")
                if audio_path:
                    return {
                        "success": True,
                        "audio_path": audio_path,
                        "audio_url": _build_audio_data_url(audio_path),
                        "tts_provider": provider,
                        "tts_fallback_used": False,
                        "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
                        "realtime_tts_endpoint": endpoint,
                        "cp3_invoked": False,
                        "tts_primary_error": "",
                        "audio_error": "",
                    }
            raw_body = raw_bytes.decode("utf-8", errors="replace")
            data = json.loads(raw_body or "{}")
            audio_path, audio_url = _resolve_audio_path_from_qwen(data, project_root, instance_id)
            if audio_path:
                return {
                    "success": True,
                    "audio_path": audio_path,
                    "audio_url": audio_url,
                    "tts_provider": provider,
                    "tts_fallback_used": False,
                    "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
                    "realtime_tts_endpoint": endpoint,
                    "cp3_invoked": False,
                    "tts_primary_error": "",
                    "audio_error": "",
                }
            last_error = f"{route or '/'}:no_audio_path"
        except Exception as exc:
            last_error = f"{route or '/'}:{exc}"
            continue
    return {
        "success": False,
        "audio_path": None,
        "audio_url": None,
        "tts_provider": provider,
        "tts_fallback_used": False,
        "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
        "realtime_tts_endpoint": endpoint,
        "cp3_invoked": False,
        "tts_primary_error": last_error or "realtime_tts_synthesis_failed",
        "audio_error": last_error or "realtime_tts_synthesis_failed",
    }


def _speak_with_qwen_tts(text, instance_id="wsl", active_local_model="llama3.2:1b", project_root="."):
    last_result = None
    for endpoint in _qwen_tts_endpoints():
        result = _speak_with_realtime_tts(
            text,
            instance_id=instance_id,
            active_local_model=active_local_model,
            project_root=project_root,
            endpoint=endpoint,
            provider="qwen",
        )
        if result.get("success") and result.get("audio_path"):
            return result
        last_result = result
    return last_result or {
        "success": False,
        "audio_path": None,
        "audio_url": None,
        "tts_provider": "qwen",
        "tts_fallback_used": False,
        "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
        "realtime_tts_endpoint": _active_realtime_tts_endpoint(),
        "cp3_invoked": False,
        "tts_primary_error": "qwen_tts_no_endpoint_result",
        "audio_error": "qwen_tts_no_endpoint_result",
    }


def _speak_with_kokoro_fallback(text, voice_instance=None, instance_id="wsl", active_local_model="llama3.2:1b"):
    if voice_instance is None:
        audio_runtime.ensure_audio_adapters()
        if not audio_runtime.TTS_AVAILABLE or audio_runtime.KokoroBaseline is None:
            return {
                "success": False,
                "audio_path": None,
                "audio_url": None,
                "tts_provider": "kokoro",
                "tts_fallback_used": True,
                "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
                "realtime_tts_endpoint": _active_realtime_tts_endpoint(),
                "cp3_invoked": False,
                "tts_primary_error": "",
                "audio_error": "native_kokoro_unavailable",
            }
        try:
            voice_instance = audio_runtime.KokoroBaseline()
        except Exception as e:
            return {
                "success": False,
                "audio_path": None,
                "audio_url": None,
                "tts_provider": "kokoro",
                "tts_fallback_used": True,
                "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
                "realtime_tts_endpoint": _active_realtime_tts_endpoint(),
                "cp3_invoked": False,
                "tts_primary_error": "",
                "audio_error": str(e),
            }
    try:
        result = voice_instance.synthesize(
            text,
            speaker_id=instance_id,
            orb_id=instance_id,
            intelligence_provider=active_local_model,
        )
        audio_path = result.get("audio_path") if isinstance(result, dict) else None
        return {
            "success": bool(audio_path),
            "audio_path": audio_path,
            "audio_url": _build_audio_data_url(audio_path) if audio_path else None,
            "tts_provider": "kokoro",
            "tts_fallback_used": True,
            "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
            "realtime_tts_endpoint": _active_realtime_tts_endpoint(),
            "cp3_invoked": False,
            "tts_primary_error": "",
            "audio_error": "" if audio_path else "kokoro_no_audio_path",
        }
    except Exception as e:
        return {
            "success": False,
            "audio_path": None,
            "audio_url": None,
            "tts_provider": "kokoro",
            "tts_fallback_used": True,
            "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
            "cp3_invoked": False,
            "tts_primary_error": "",
            "audio_error": str(e),
        }


class TTSClient:
    """Universal TTS client: resident real-time service primary."""

    def __init__(self, project_root, instance_id="wsl", active_local_model="llama3.2:1b"):
        self.project_root = Path(project_root)
        self.instance_id = instance_id
        self.active_local_model = active_local_model
        self.voice_instance = None
        self.tts_provider = _preferred_tts_provider()
        self.tts_fallback_used = False
        self.tts_primary_error = ""

    def set_voice_instance(self, voice_instance):
        self.voice_instance = voice_instance

    def speak(self, text):
        """Attempt configured primary TTS first. Never silently succeed without audio."""
        require_realtime = os.getenv("ORB_REALTIME_TTS_REQUIRE_READY", "1").strip().lower() in {"1", "true", "yes", "on"}
        provider = _preferred_tts_provider()

        if provider in {"qwen", "qwen3", "qwen-tts", "qwen3-tts"}:
            qwen_result = _speak_with_qwen_tts(
                text,
                instance_id=self.instance_id,
                active_local_model=self.active_local_model,
                project_root=str(self.project_root),
            )
            if qwen_result.get("success") and qwen_result.get("audio_path"):
                self.tts_provider = "qwen"
                self.tts_fallback_used = False
                self.tts_primary_error = ""
                qwen_result["tts_fallback_used"] = False
                return qwen_result

            self.tts_primary_error = qwen_result.get("audio_error") or "qwen_no_audio_path"
            kokoro_result = _speak_with_kokoro_fallback(
                text,
                voice_instance=self.voice_instance,
                instance_id=self.instance_id,
                active_local_model=self.active_local_model,
            )
            if kokoro_result.get("success") and kokoro_result.get("audio_path"):
                self.tts_provider = "kokoro"
                self.tts_fallback_used = True
                kokoro_result["tts_fallback_used"] = True
                kokoro_result["tts_primary_error"] = self.tts_primary_error
                return kokoro_result

            return {
                "success": False,
                "audio_path": None,
                "audio_url": None,
                "tts_provider": "qwen",
                "tts_fallback_used": bool(kokoro_result.get("success")),
                "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
                "realtime_tts_endpoint": _active_realtime_tts_endpoint(),
                "cp3_invoked": bool(kokoro_result.get("cp3_invoked")),
                "tts_primary_error": self.tts_primary_error,
                "audio_error": kokoro_result.get("audio_error") or self.tts_primary_error,
            }

        if provider == "kokoro":
            kokoro_result = _speak_with_kokoro_fallback(
                text,
                voice_instance=self.voice_instance,
                instance_id=self.instance_id,
                active_local_model=self.active_local_model,
            )
            if kokoro_result.get("success") and kokoro_result.get("audio_path"):
                self.tts_provider = "kokoro"
                self.tts_fallback_used = False
                self.tts_primary_error = ""
                kokoro_result["tts_fallback_used"] = False
                return kokoro_result

            self.tts_primary_error = kokoro_result.get("audio_error") or "kokoro_no_audio_path"
            qwen_result = _speak_with_qwen_tts(
                text,
                instance_id=self.instance_id,
                active_local_model=self.active_local_model,
                project_root=str(self.project_root),
            )
            if qwen_result.get("success") and qwen_result.get("audio_path"):
                self.tts_provider = "qwen"
                self.tts_fallback_used = True
                qwen_result["tts_fallback_used"] = True
                qwen_result["tts_primary_error"] = self.tts_primary_error
                return qwen_result

            return {
                "success": False,
                "audio_path": None,
                "audio_url": None,
                "tts_provider": "kokoro",
                "tts_fallback_used": bool(qwen_result.get("success")),
                "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
                "realtime_tts_endpoint": _active_realtime_tts_endpoint(),
                "cp3_invoked": bool(kokoro_result.get("cp3_invoked")),
                "tts_primary_error": self.tts_primary_error,
                "audio_error": qwen_result.get("audio_error") or self.tts_primary_error,
            }

        realtime_result = _speak_with_realtime_tts(
            text,
            instance_id=self.instance_id,
            active_local_model=self.active_local_model,
            project_root=str(self.project_root),
        )
        if realtime_result.get("success") and realtime_result.get("audio_path"):
            self.tts_provider = realtime_result.get("tts_provider") or _preferred_tts_provider()
            self.tts_fallback_used = False
            self.tts_primary_error = ""
            return realtime_result

        self.tts_primary_error = realtime_result.get("audio_error") or "realtime_tts_no_audio_path"
        if require_realtime:
            return {
                "success": False,
                "audio_path": None,
                "audio_url": None,
                "tts_provider": _preferred_tts_provider(),
                "tts_fallback_used": False,
                "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
                "realtime_tts_endpoint": _active_realtime_tts_endpoint(),
                "cp3_invoked": False,
                "tts_primary_error": self.tts_primary_error,
                "audio_error": self.tts_primary_error,
            }

        kokoro_result = _speak_with_kokoro_fallback(
            text,
            voice_instance=self.voice_instance,
            instance_id=self.instance_id,
            active_local_model=self.active_local_model,
        )
        if kokoro_result.get("success") and kokoro_result.get("audio_path"):
            self.tts_provider = "kokoro"
            self.tts_fallback_used = True
            return kokoro_result

        return {
            "success": False,
            "audio_path": None,
            "audio_url": None,
            "tts_provider": _preferred_tts_provider(),
            "tts_fallback_used": bool(kokoro_result.get("success")),
            "qwen_tts_endpoint": _active_qwen_tts_endpoint(),
            "realtime_tts_endpoint": _active_realtime_tts_endpoint(),
            "cp3_invoked": bool(kokoro_result.get("cp3_invoked")),
            "tts_primary_error": self.tts_primary_error,
            "audio_error": (
                kokoro_result.get("audio_error")
                or "realtime_tts_and_kokoro_failed"
            ),
        }

    def get_health(self):
        return _probe_qwen_tts_health()

